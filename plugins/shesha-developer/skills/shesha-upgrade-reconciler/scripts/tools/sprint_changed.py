"""alias: the old command name `sprint-changed` runs `branch-changed`"""
from tools.branch_changed import main   # noqa: F401  (shrec.py calls main(args))

if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
