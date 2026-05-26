import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from src.api.deps import get_db
from src.services.model_preset import ModelPresetService, ModelPresetCreate

router = APIRouter()


class PresetCreateRequest(BaseModel):
    name: str
    provider: str
    model_name: str
    litellm_model_string: str = ""
    api_key_plaintext: str = ""
    api_key_label: str = "default"
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    max_retries: int = 3
    retry_delay_sec: float = 2.0


@router.get("/")
async def list_presets(db: AsyncSession = Depends(get_db)):
    svc = ModelPresetService(db)
    presets = await svc.list_presets()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "provider": p.provider,
            "model_name": p.model_name,
            "litellm_model_string": p.litellm_model_string,
            "is_active": p.is_active,
            "max_retries": p.max_retries,
        }
        for p in presets
    ]


@router.post("/", status_code=201)
async def create_preset(data: PresetCreateRequest, db: AsyncSession = Depends(get_db)):
    svc = ModelPresetService(db)
    try:
        preset = await svc.create_preset(ModelPresetCreate(
            name=data.name,
            provider=data.provider,
            model_name=data.model_name,
            litellm_model_string=data.litellm_model_string or f"{data.provider}/{data.model_name}",
            api_key_plaintext=data.api_key_plaintext,
            api_key_label=data.api_key_label,
            cost_per_1k_input=data.cost_per_1k_input,
            cost_per_1k_output=data.cost_per_1k_output,
            max_retries=data.max_retries,
            retry_delay_sec=data.retry_delay_sec,
        ))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(preset.id), "name": preset.name, "message": "模型预设已创建"}


@router.get("/{preset_id}")
async def get_preset(preset_id: str, db: AsyncSession = Depends(get_db)):
    svc = ModelPresetService(db)
    try:
        preset, api_key = await svc.get_preset_with_key(uuid.UUID(preset_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "id": str(preset.id),
        "name": preset.name,
        "provider": preset.provider,
        "model_name": preset.model_name,
        "litellm_model_string": preset.litellm_model_string,
        "is_active": preset.is_active,
        "max_retries": preset.max_retries,
        "has_api_key": api_key is not None,
    }


@router.delete("/{preset_id}")
async def delete_preset(preset_id: str, db: AsyncSession = Depends(get_db)):
    svc = ModelPresetService(db)
    try:
        await svc.delete_preset(uuid.UUID(preset_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "模型预设已删除"}
