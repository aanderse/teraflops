{ buildPythonApplication, setuptools, setuptools-scm, termcolor }:

buildPythonApplication {
  pname = "teraflops";
  version = "0.0.1";
  format = "pyproject";

  src = ./..;

  nativeBuildInputs = [ setuptools setuptools-scm ];
  propagatedBuildInputs = [ termcolor ];
}
