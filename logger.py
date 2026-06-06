import os
import yaml
import logging.config

def setup_logging(default_path='logging.yaml', default_level=logging.DEBUG):
    if os.path.exists(default_path):
        with open(default_path, 'rt', encoding='utf-8') as f:
            config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

setup_logging()
logger = logging.getLogger("agent")
