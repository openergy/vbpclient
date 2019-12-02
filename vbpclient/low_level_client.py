import os
import requests

from .rest_api_client import RESTClient
from .tasker import Task


class LowLevelClient:
    """
    Encapsulates two clients one for upload (requests.Session), one for download (RESTClient).
    """
    _conf = {
        "root_endpoint": "api/v1",
        "is_on_resource": "/",
        "verify_ssl": True,
    }

    def __init__(self, credentials, host, port):
        """
        Creates two low level clients and implements direct wrappers to to their functionality.

        Parameters
        ----------
        credentials  : tuple containing exactly 2 strings.
                   first element is the long, second element is the password.
        """
        self.client = RESTClient(credentials=credentials, host=host, port=port, **self._conf)
        self.upload_client = requests.Session()

    def retrieve(self, resource, resource_id):
        return self.client.retrieve(resource, resource_id)

    def create(self, resource, data):
        return self.client.create(resource, data)

    def list(self, resource, params=None):
        return self.client.list(resource, params=params)["data"]

    def list_iter_all(self, resource, params=None):
        return self.client.list_iter_all(resource, params=params)

    def destroy(self, resource, resource_id):
        response = self.client.destroy(resource, resource_id)
        if response:
            return response["user_task"]
        else:
            return None

    def partial_update(self, resource, resource_id, data):
        return self.client.partial_update(resource, resource_id, data)

    def detail_route(
            self,
            resource,
            resource_id,
            http_method,
            method_name,
            params=None,
            data=None,
            return_json=True,
            send_json=True,
            content_type=None):
        return self.client.detail_route(
            resource,
            resource_id,
            http_method,
            method_name,
            data=data,
            params=params,
            return_json=return_json,
            send_json=send_json,
            content_type=content_type,
        )

    def import_data(self, resource, resource_id, import_format, **kwargs):
        response = self.detail_route(
            resource,
            resource_id,
            "PATCH",
            "import_data",
            data=dict(import_format=import_format, **kwargs),
        )
        if response:
            task_id = response["user_task"]
            import_task = Task(task_id, self)
            success = import_task.wait_for_completion(period=100)
            if not success:
                raise RuntimeError(
                    f"Import failed. Error:\n"
                    f"{import_task.message}"
                )

    def upload(self, resource, resource_id, path, detail_route="upload_url"):
        upload_url = self.detail_route(resource, resource_id, "GET", detail_route)["blob_url"]
        with open(os.path.realpath(path), "rb") as f:
            response = self.upload_client.put(
                upload_url,
                f.read(),
                headers={"x-ms-blob-type": "BlockBlob"}
            )
            self.client.check_rep(response)

    def download(self, resource, resource_id, detail_route="blob_url", path=None):
        """
        Returns
        -------
        bytes or None
        """
        download_url = self.detail_route(resource, resource_id, "GET", detail_route)["blob_url"]
        return self._download(download_url, path=path)

    def export(self, resource, resource_id, detail_route="export_data", export_format=None, params=None, path=None):
        params = dict() if params is None else params
        if export_format is not None:
            params["export_format"] = export_format
        response = self.detail_route(resource, resource_id, "GET", detail_route, params=params)
        export_task = Task(response["user_task"], self)
        success = export_task.wait_for_completion(period=100)
        if not success:
            raise RuntimeError(f"Import failed. Error:\n{export_task.message}\n{export_task.response['_out_text']}")
        download_url = export_task.response["data"]["blob_url"]
        return self._download(download_url, path=path)

    def _download(self, download_url, path=None):
        response = self.upload_client.get(
            download_url
        )
        if isinstance(response.content, bytes):
            if path is None:
                return response.content
            else:
                with open(path, "wb") as f:
                    f.write(response.content)
        elif isinstance(response.content, str):
            if path is None:
                return response.content.encode("utf-8")
            else:
                with open(path, "w") as f:
                    f.write(response.content)
        else:
            raise ValueError("Response content is neither str nor bytes")
