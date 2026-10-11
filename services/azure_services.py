from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AzureStatus:
    service: str
    configured: bool
    message: str


class AzureDocumentIntelligenceService:
    def __init__(self) -> None:
        self.endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
        self.key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")

    def status(self) -> AzureStatus:
        configured = bool(self.endpoint and self.key)
        return AzureStatus(
            "Azure AI Document Intelligence",
            configured,
            "Endpoint and key detected." if configured else "Disabled or credentials are missing; local parser remains active.",
        )

    def extract_text(self, data: bytes) -> str:
        if not (self.endpoint and self.key):
            raise RuntimeError("Azure AI Document Intelligence is not configured.")
        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise RuntimeError("Install azure-ai-documentintelligence to use Azure OCR.") from exc
        client = DocumentIntelligenceClient(self.endpoint, AzureKeyCredential(self.key))
        poller = client.begin_analyze_document("prebuilt-layout", body=data)
        result = poller.result()
        text = (result.content or "").strip()
        if not text:
            raise RuntimeError("Azure OCR returned no text.")
        return text


class AzureLanguageService:
    def __init__(self) -> None:
        self.endpoint = os.getenv("AZURE_LANGUAGE_ENDPOINT", "")
        self.key = os.getenv("AZURE_LANGUAGE_KEY", "")

    def status(self) -> AzureStatus:
        configured = bool(self.endpoint and self.key)
        return AzureStatus(
            "Azure AI Language",
            configured,
            "Endpoint and key detected." if configured else "Disabled or credentials are missing; local extraction remains active.",
        )

    def extract_entities(self, text: str) -> list[dict[str, str | float]]:
        if not (self.endpoint and self.key):
            raise RuntimeError("Azure AI Language is not configured.")
        try:
            from azure.ai.textanalytics import TextAnalyticsClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise RuntimeError("Install azure-ai-textanalytics to use Azure Language.") from exc
        client = TextAnalyticsClient(self.endpoint, AzureKeyCredential(self.key))
        response = client.recognize_entities([text[:5000]])[0]
        if response.is_error:
            raise RuntimeError(f"Azure Language error: {response.error.code}")
        return [
            {"text": entity.text, "category": entity.category, "confidence": float(entity.confidence_score)}
            for entity in response.entities
        ]


class AzureBlobStorageService:
    def __init__(self) -> None:
        self.connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        self.account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL", "")
        self.container_name = os.getenv("AZURE_STORAGE_CONTAINER", "resumes")
        self._resource_not_found_error = Exception

    def status(self) -> AzureStatus:
        configured = bool(self.connection_string or self.account_url)
        return AzureStatus(
            "Azure Blob Storage",
            configured,
            "Managed identity account URL detected; verify its Storage Blob Data Contributor role."
            if self.account_url
            else "Connection string detected; keep it in App Service settings or Key Vault."
            if self.connection_string
            else "Disabled or storage configuration is missing; local storage remains active.",
        )

    def _container(self):
        if not (self.connection_string or self.account_url):
            raise RuntimeError("Azure Blob Storage is not configured.")
        try:
            from azure.storage.blob import BlobServiceClient
            from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
        except ImportError as exc:
            raise RuntimeError("Install azure-storage-blob to use Azure storage.") from exc
        if self.account_url:
            try:
                from azure.identity import DefaultAzureCredential
            except ImportError as exc:
                raise RuntimeError("Install azure-identity to use managed identity for Azure storage.") from exc
            service = BlobServiceClient(account_url=self.account_url, credential=DefaultAzureCredential())
        else:
            service = BlobServiceClient.from_connection_string(self.connection_string)
        container = service.get_container_client(self.container_name)
        try:
            container.create_container()
        except ResourceExistsError:
            pass
        self._resource_not_found_error = ResourceNotFoundError
        return container

    def upload(self, blob_name: str, data: bytes) -> None:
        self._container().upload_blob(blob_name, data, overwrite=True)

    def delete(self, blob_name: str) -> None:
        container = self._container()
        try:
            container.delete_blob(blob_name, delete_snapshots="include")
        except self._resource_not_found_error:
            pass


def all_azure_statuses() -> list[AzureStatus]:
    return [
        AzureDocumentIntelligenceService().status(),
        AzureLanguageService().status(),
        AzureBlobStorageService().status(),
    ]

