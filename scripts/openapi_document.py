"""Write the application's OpenAPI document to stdout.

A gate rather than a convenience, which is why it is in the repository at all:
`just console-types` regenerates the console's TypeScript from this, and CI
fails when the result differs from what was committed. That is the same shape
as the migration drift test — two representations of one contract, with
something that notices when they disagree.

**Builds the application rather than asking a running server.** Starting one to
answer a question the code can answer directly would put a port, a database and
a startup race into a step that has to work inside a CI job with none of them.
``create_app`` reads no settings, deliberately, so this costs an import.
"""

import json
import sys

from bacteria.app.views import create_app


def main() -> int:
    json.dump(create_app().openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
