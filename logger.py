"""
Logger setup.
"""
import logging
from config import APP_LOG_FILE

def setup_logger():
    logger = logging.getLogger("BTC_Bot")
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    
    # File handler
    fh = logging.FileHandler(APP_LOG_FILE)
    fh.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(ch)
        logger.addHandler(fh)
        
    return logger

logger = setup_logger()
