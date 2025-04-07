
import argparse

def confirm():
  parser = argparse.ArgumentParser(add_help=False)
  parser.add_argument('--confirm', action='store_true', help='confirm dangerous operations; do not ask')

  return parser

def no_keys():
  parser = argparse.ArgumentParser(add_help=False)
  parser.add_argument('--no-keys', action='store_true', help='do not upload secret keys set in `deployment.keys`')

  return parser

def on():
  parser = argparse.ArgumentParser(add_help=False)
  parser.add_argument('--on', metavar='<NODES>', help='select a list of nodes to deploy to')

  return parser

def with_drvs():
  parser = argparse.ArgumentParser(add_help=False)
  parser.add_argument('--with-drvs', metavar='<FILE>', help='a file including json key value pairs of node name and the associated top level evaluated drv')

  return parser
