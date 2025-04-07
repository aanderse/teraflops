
import contextlib

from rich.live import Live
from rich.style import Style
from rich.table import Table
from rich.text import Text

from rich.progress import (
  Progress,
  ProgressColumn,
  SpinnerColumn,
  TextColumn,
)

INFO_D = '[[green]INFO [/]]'
WARN_D = '[[yellow]WARN [/]]'
ERROR_D = '[[red]ERROR[/]]'

class TimeElapsedColumn(ProgressColumn):
  """Renders time elapsed."""

  def render(self, task: "Task") -> Text:
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

class Console:
  def __init__(self, verbose=False):
    import rich

    self.rich = rich.console.Console(emoji=False)
    self.use_table = verbose

  def print(self, text):
    self.rich.print(text)

  def info(self, text):
    self.rich.print(f'{INFO_D} {text}')

  def warn(self, text):
    self.rich.print(f'{WARN_D} {text}')

  def error(self, text):
    self.rich.print(f'{ERROR_D} {text}')

  @contextlib.contextmanager
  def refresh(self):
    if self.use_table:
      self.table = Table.grid('', '', '') # node, separator, message
      with Live(self.table) as live:
        try:
          yield
        finally:
          live.refresh()
    else:
      with Progress(TextColumn('{task.fields[node]}', justify='right'), SpinnerColumn('clock', style=Style.null(), finished_text=':white_check_mark:'), TimeElapsedColumn(), '{task.description}', console=self.rich) as progress:
        self.progress = progress
        yield


  def message(self, name, description=''):
    if self.use_table:
      assert self.table

      if description != '':
        self.table.add_row(f'[bold]{name}', ' | ', description)
      return name
    else:
      assert self.progress
      return self.progress.add_task(description, total=1, node=f'[bold]{name}')

  def update(self, msg, text, status=None):
    if self.use_table:
      assert self.table
      markup = 'bold'
      if status == 'success':
        markup = markup + ' green'
      if status == 'failure':
        markup = markup + ' red'
      self.table.add_row(f'[{markup}]{msg}', ' | ', text)
    elif text != '':
      assert self.progress
      name = self.progress.tasks[msg].fields['node']

      extra_args = {}
      if status == 'success':
        extra_args = {'advance': 1, 'node': f'[bold green]{name}'}
      if status == 'failure':
        extra_args = {'node': f'[bold red]{name}'}

      self.progress.update(msg, description=text, **extra_args)
