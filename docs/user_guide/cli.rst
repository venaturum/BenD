.. _cli:

=============
Command Line
=============

.. code-block:: console

  Usage:

      Usage: bendee simple_milp [OPTIONS] FILEPATH

      Run a simple milp benders

      Options:
      -f, --framework [callback|iterative]
                                      Which framework to use
      -l, --lpform [primal|dual]      Subproblem form
      -r, --subreturn [subgradient|duals]
                                      Subproblem return type
      -l, --loglevel TEXT             Logging level
      --help                          Show this message and exit.
