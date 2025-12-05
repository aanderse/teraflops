
import shutil

class BinaryNotFoundError(Exception):
  pass

def terraform():
  for exe in [ 'terraform', 'tofu' ]:
    path = shutil.which(exe)
    if path:
      return path

  raise BinaryNotFoundError('could not find a suitable terraform binary in $PATH')
