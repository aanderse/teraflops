
# asyncio doesn't have an equivalent exception to subprocess so roll our own
class CalledProcessError(Exception):
  def __init__(self, returncode, stdout=None, stderr=None):
    self.returncode = returncode
    self.stdout = stdout
    self.stderr = stderr
