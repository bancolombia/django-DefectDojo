from split_settings.tools import optional, include

# See https://documentation.defectdojo.com/getting_started/configuration/ for options
# how to tune the configuration to your needs.

include(
    "settings.dist.py",
    optional("local_settings.py"),
)