{ buildPythonApplication, setuptools, setuptools-scm, rich }:

buildPythonApplication {
  pname = "teraflops";
  version = "0.1.1";
  format = "pyproject";

  src = ./..;

  nativeBuildInputs = [ setuptools setuptools-scm ];
  propagatedBuildInputs = [ rich ];
}
