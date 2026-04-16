from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ScanMode = Literal["collection_paper", "collection_all", "single_item", "parent_keys", "global"]
PdfParser = Literal["auto", "mineru", "pypdf"]


class PathSettings(BaseModel):
    provider_config_path: str | None = None
    template_dir_path: str | None = None
    obsidian_vault_path: str | None = None
    obsidian_folder_path: str | None = None
    zotero_db_path: str | None = None
    zotero_storage_path: str | None = None


class ProviderUpsert(BaseModel):
    name: str
    model: str = ""
    provider_type: Literal["openai_compatible", "gemini"] = "openai_compatible"
    base_url: str = ""
    env_var: str = ""
    custom_models: list[str] | str = Field(default_factory=list)
    api_key: str | None = None
    is_new: bool = False


class ProviderConnectionTest(BaseModel):
    name: str = ""
    model: str = ""
    provider_type: Literal["openai_compatible", "gemini"] = "openai_compatible"
    base_url: str = ""
    api_key: str | None = None


class MineruSettings(BaseModel):
    token: str | None = None
    model_version: str | None = None
    language: str | None = None


class JobStartRequest(BaseModel):
    provider: str
    model: str
    template_name: str
    scan_mode: ScanMode
    collections: list[str] = Field(default_factory=list)
    collection_item_key: str | None = None
    parent_item_keys: list[str] = Field(default_factory=list)
    allow_global_scan: bool = False
    limit: int = Field(default=1, ge=1)
    since_days: int = Field(default=0, ge=0)
    enable_thinking: bool = False
    dry_run: bool = False
    force: bool = False
    pdf_parser: PdfParser = "auto"
    mineru_model_version: str = "vlm"
    mineru_language: str = "en"


class ApiError(BaseModel):
    detail: str


class AnyPayload(BaseModel):
    data: dict[str, Any]
