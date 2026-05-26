import uuid
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.agent import ModelPreset, ApiKey
from src.repositories.agent_repo import ModelPresetRepository
from src.utils.security import encrypt_api_key, decrypt_api_key, get_key_prefix
from src.core.exceptions import PlatformError


@dataclass
class ModelPresetCreate:
    name: str
    provider: str
    model_name: str
    litellm_model_string: str
    default_params: dict | None = None
    api_key_plaintext: str = ""
    api_key_label: str = "default"
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    max_retries: int = 3
    retry_delay_sec: float = 2.0


class ModelPresetService:
    def __init__(self, session: AsyncSession):
        self.repo = ModelPresetRepository(session)
        self.session = session

    async def create_preset(self, data: ModelPresetCreate) -> ModelPreset:
        existing = await self.repo.get_by_name(data.name)
        if existing:
            raise PlatformError(f"模型预设 '{data.name}' 已存在")

        preset = ModelPreset(
            name=data.name,
            provider=data.provider,
            model_name=data.model_name,
            litellm_model_string=data.litellm_model_string,
            default_params=data.default_params or {},
            cost_per_1k_input=data.cost_per_1k_input,
            cost_per_1k_output=data.cost_per_1k_output,
            max_retries=data.max_retries,
            retry_delay_sec=data.retry_delay_sec,
        )
        preset = await self.repo.create(preset)

        if data.api_key_plaintext:
            api_key = ApiKey(
                preset_id=preset.id,
                key_label=data.api_key_label,
                encrypted_key=encrypt_api_key(data.api_key_plaintext),
                key_prefix=get_key_prefix(data.api_key_plaintext),
            )
            self.session.add(api_key)
            await self.session.flush()

        return preset

    async def list_presets(self) -> list[ModelPreset]:
        return await self.repo.list_all()

    async def get_preset(self, preset_id: uuid.UUID) -> ModelPreset:
        preset = await self.repo.get(preset_id)
        if not preset:
            raise PlatformError(f"模型预设不存在: {preset_id}")
        return preset

    async def get_preset_with_key(self, preset_id: uuid.UUID) -> tuple[ModelPreset, str | None]:
        preset = await self.get_preset(preset_id)
        api_key = None
        if preset.api_keys:
            active_keys = [k for k in preset.api_keys if k.is_active]
            if active_keys:
                api_key = decrypt_api_key(active_keys[0].encrypted_key)
        return preset, api_key

    async def delete_preset(self, preset_id: uuid.UUID):
        preset = await self.get_preset(preset_id)
        await self.repo.delete(preset)
