"""Refactored console module with improved API and type safety."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from rich.live import Live
from rich.markup import escape
from rich.progress import Progress, ProgressColumn, SpinnerColumn, TextColumn
from rich.style import Style
from rich.table import Table
from rich.text import Text


class Status(Enum):
  """Status values for task completion."""

  SUCCESS = 'success'
  FAILURE = 'failure'


class TimeElapsedColumn(ProgressColumn):
  """Renders time elapsed."""

  def render(self, task) -> Text:
    """Show time elapsed."""
    elapsed = task.finished_time if task.finished else task.elapsed
    if elapsed is None:
      return Text('')

    value = max(0, int(elapsed))
    if value > 99:
      m, s = divmod(value, 60)
      value = f'{m}m{s}s' if m > 0 else f'{s}s'
    else:
      value = f'{value}s'

    return Text(value)


class TaskHandle(Protocol):
  """Protocol defining the interface for task handles."""

  def update(self, text: str, status: Status | None = None) -> None:
    """Update the task with new text and optional status."""
    ...


@dataclass
class TraceTaskHandle:
  """Handle for trace-mode linear output."""

  _console: Console
  _name: str

  def update(self, text: str, status: Status | None = None) -> None:
    if not text:
      return

    # Print as a trace log with node name prefix
    if status == Status.SUCCESS:
      node_display = f'[green]{self._name}[/]'
    elif status == Status.FAILURE:
      node_display = f'[red]{self._name}[/]'
    else:
      node_display = self._name

    timestamp_prefix = self._console._format_timestamp()
    self._console._console.print(f'{timestamp_prefix}[[dim]TRACE[/]] {node_display}: {escape(text)}')


@dataclass
class TableTaskHandle:
  """Handle for updating table-based output."""

  _table: Table
  _name: str
  _format_timestamp: Callable[[], str]

  def update(self, text: str, status: Status | None = None) -> None:
    if not text:
      return

    markup = 'bold'
    if status == Status.SUCCESS:
      markup = 'bold green'
    elif status == Status.FAILURE:
      markup = 'bold red'

    # Add timestamp prefix if enabled
    timestamp_prefix = self._format_timestamp()
    self._table.add_row(f'{timestamp_prefix}[{markup}]{self._name}', ' | ', escape(text))


@dataclass
class ProgressTaskHandle:
  """Handle for updating progress-based output."""

  _progress: Progress
  _task_id: int

  def update(self, text: str, status: Status | None = None) -> None:
    if not text:
      return

    name = self._progress.tasks[self._task_id].fields['node']

    update_args = {'description': escape(text)}
    if status == Status.SUCCESS:
      update_args['advance'] = 1
      update_args['node'] = f'[bold green]{name}'
    elif status == Status.FAILURE:
      update_args['node'] = f'[bold red]{name}'

    self._progress.update(self._task_id, **update_args)


class RefreshContext:
  """Context manager that provides task tracking capabilities."""

  def __init__(self, console: Console, live_context):
    self._console = console
    self._live_context = live_context

  def __enter__(self) -> RefreshContext:
    self._live_context.__enter__()
    return self

  def __exit__(self, *args):
    return self._live_context.__exit__(*args)

  def message(self, name: str, description: str = '', status: Status | None = None) -> TaskHandle:
    """Create a new task and return a handle for updating it."""
    return self._console._create_task(name, description, status)


class Console:
  """Console abstraction for displaying progress and messages."""

  # message prefixes
  _TRACE = '[[dim]TRACE[/]]'
  _INFO = '[[green]INFO [/]]'
  _WARN = '[[yellow]WARN [/]]'
  _ERROR = '[[red]ERROR[/]]'

  def __init__(self, verbosity: int = 0):
    """
    Initialize the console.

    Args:
        verbosity: Verbosity level (0=normal, 1=verbose/table, 2+=trace with timestamps)
    """
    from rich.console import Console as RichConsole

    self._console = RichConsole(emoji=False)
    self._verbosity = verbosity

    # these are only valid inside refresh() context
    self._table: Table | None = None
    self._progress: Progress | None = None

  def _format_timestamp(self) -> str:
    """Format current timestamp for display (shown in trace mode only)."""
    if self._verbosity < 2:
      return ''
    return f'[dim]{datetime.now().strftime("%H:%M:%S")}[/] '

  def print(self, text: str) -> None:
    """Print unformatted text."""
    self._console.print(text, markup=False)

  def trace(self, text: str) -> None:
    """Print a trace message (only shown with -vv or higher)."""
    if self._verbosity >= 2:
      self._console.print(f'{self._format_timestamp()}{self._TRACE} {text}')

  def info(self, text: str) -> None:
    """Print an info message."""
    self._console.print(f'{self._format_timestamp()}{self._INFO} {text}')

  def warn(self, text: str) -> None:
    """Print a warning message."""
    self._console.print(f'{self._format_timestamp()}{self._WARN} {text}')

  def error(self, text: str) -> None:
    """Print an error message."""
    self._console.print(f'{self._format_timestamp()}{self._ERROR} {text}')

  @contextlib.contextmanager
  def refresh(self) -> RefreshContext:
    """
    Enter a refresh context for tracking multiple concurrent tasks.

    Returns a context manager that provides the message() method for
    creating task handles.

    Example:
        with console.refresh() as ctx:
            task = ctx.message('server1', 'Starting')
            task.update('Running')
            task.update('Complete', Status.SUCCESS)
    """
    # When trace logging is enabled (-vv+), disable table for linear output
    if self._verbosity >= 2:
      # No table, task updates will print as plain trace logs
      yield RefreshContext(self, contextlib.nullcontext())
    elif self._verbosity >= 1:
      self._table = Table.grid('', '', '')  # node, separator, message
      live = Live(self._table, console=self._console)
      try:
        with live:
          yield RefreshContext(self, contextlib.nullcontext())
          live.refresh()
      finally:
        self._table = None
    else:
      progress = Progress(
        TextColumn('{task.fields[node]}', justify='right'),
        SpinnerColumn('clock', style=Style.null(), finished_text=':white_check_mark:'),
        TimeElapsedColumn(),
        '{task.description}',
        console=self._console,
      )
      try:
        with progress:
          self._progress = progress
          yield RefreshContext(self, contextlib.nullcontext())
      finally:
        self._progress = None

  def _create_task(
    self, name: str, description: str = '', status: Status | None = None
  ) -> TaskHandle:
    """Internal method called by RefreshContext to create tasks."""
    if self._table is not None:
      handle = TableTaskHandle(self._table, name, self._format_timestamp)
      if description:
        handle.update(description, status)
      return handle
    elif self._progress is not None:
      task_id = self._progress.add_task(description, total=1, node=f'[bold]{name}')
      handle = ProgressTaskHandle(self._progress, task_id)
      if status is not None:
        handle.update(description, status)
      return handle
    else:
      # Trace mode (verbosity >= 2) - print directly as trace logs
      handle = TraceTaskHandle(self, name)
      if description:
        handle.update(description, status)
      return handle
