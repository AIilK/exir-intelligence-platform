from app.integrations.base_connector import BaseConnector


class ExcelConnector(BaseConnector):

    def __init__(self, config):

        self.config = config


    def connect(self):

        pass


    def disconnect(self):

        pass


    def test_connection(self):

        pass


    def fetch_data(self, sheet_name):

        pass