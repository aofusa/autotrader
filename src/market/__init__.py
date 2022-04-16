import json
import uuid
from logging import getLogger, StreamHandler, DEBUG, INFO, Formatter


handler = StreamHandler()


class JsonFormatter(Formatter):

    def _str2json(self, msg):
        if type(msg) is str or \
            type(msg) is dict or \
            type(msg) is list:
            return json.dumps(msg)
        return msg

    def format(self, record):
        record.msg = self._str2json(record.msg)
        return super().format(record)


def anonymization(x):
    data = str(x)
    if len(data) < 1:
        return data
    elif len(data) == 1:
        return '*'
    elif len(data) <= 4:
        return data[0] + '*'*(len(data)-1)
    else:
        return data[0] + data[1] + '*'*(len(data)-3) + data[-1]


def update_transaction_id(transaction_id=uuid.uuid4().hex):
    formatter = JsonFormatter('{"timestamp": "%(asctime)-15s", "transaction-id": ' + f'"{transaction_id}"' + ', "level": "%(levelname)s", "message": %(message)s}')
    handler.setFormatter(formatter)


def get_module_logger(modname):
    formatter = JsonFormatter('{"timestamp": "%(asctime)-15s", "transaction-id": ' + f'"{uuid.uuid4().hex}"' + ', "level": "%(levelname)s", "message": %(message)s}')
    logger = getLogger(modname)
    handler.setLevel(DEBUG)
    handler.setFormatter(formatter)
    logger.setLevel(DEBUG)
    logger.addHandler(handler)
    logger.propagate = False
    return logger

