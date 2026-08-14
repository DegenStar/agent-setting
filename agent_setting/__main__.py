"""支持 python -m agent_setting 直接运行。"""

import sys

from .cli import main

sys.exit(main())
