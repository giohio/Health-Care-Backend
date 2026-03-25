from typing import Annotated, List

from Application.dtos import SpecialtyDTO
from Application.use_cases.list_specialties import ListSpecialtiesUseCase
from Application.use_cases.save_specialty import SaveSpecialtyUseCase
from Domain.exceptions.domain_exceptions import SpecialtyAlreadyExistsException
from fastapi import APIRouter, Depends, HTTPException
from presentation.dependencies import get_list_specialties_use_case, get_save_specialty_use_case

router = APIRouter(prefix="/specialties", tags=["Specialties"])


@router.get("", response_model=List[SpecialtyDTO])
async def list_specialties(use_case: Annotated[ListSpecialtiesUseCase, Depends(get_list_specialties_use_case)]):
    return await use_case.execute()


@router.post("", response_model=SpecialtyDTO, responses={400: {"description": "Specialty already exists"}})
async def create_specialty(
    dto: SpecialtyDTO, use_case: Annotated[SaveSpecialtyUseCase, Depends(get_save_specialty_use_case)]
):
    try:
        return await use_case.execute(dto)
    except SpecialtyAlreadyExistsException as e:
        raise HTTPException(status_code=400, detail=str(e))
