class FeishuWarningException(Exception):
    """
    飞书卡片使用这个异常抛出时会返送 warning 提示卡片，展示给用户看的
    """
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return self.message


