from app.integrations.sqlserver_connector import SQLServerConnector
from app.integrations.api_connector import APIConnector
from app.integrations.excel_connector import ExcelConnector
from app.integrations.file_connector import FileConnector


class ConnectorFactory:

    @staticmethod
    def create(connector_type: str, config: dict):

        connector_type = connector_type.lower()

        if connector_type == "sqlserver":
            return SQLServerConnector(config)

        elif connector_type == "api":
            return APIConnector(config)

        elif connector_type == "excel":
            return ExcelConnector(config)

        elif connector_type == "file":
            return FileConnector(config)

        else:
            raise ValueError(
                f"Unsupported connector type: {connector_type}"
            )