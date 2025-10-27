"""Repositório especializado para configurações persistentes."""

from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.models.Settings import SystemSetting
from src.repository.Base_repository import BaseRepo
from src.utils.logs import logger


class SettingsRepo(BaseRepo):
    def __init__(self, session: Optional[Session] = None):
        super().__init__(SystemSetting, session=session)

    def get_by_key(self, key: str) -> Optional[SystemSetting]:
        try:
            return self.session.query(self.model).filter(self.model.key == key).first()
        except SQLAlchemyError:
            logger.exception("Erro ao obter configuração %s", key)
            return None

    def set_value(
        self,
        key: str,
        value: str,
        *,
        description: Optional[str] = None,
        commit: bool = True,
    ) -> SystemSetting:
        try:
            setting = self.get_by_key(key)
            if setting:
                setting.value = value
                if description is not None:
                    setting.description = description
            else:
                setting = SystemSetting(key=key, value=value, description=description)
                self.session.add(setting)

            if commit:
                self.session.commit()
            else:
                self.session.flush()
            return setting
        except SQLAlchemyError:
            self.session.rollback()
            logger.exception("Erro ao gravar configuração %s", key)
            raise

    def get_bool(self, key: str, default: bool = False) -> bool:
        setting = self.get_by_key(key)
        if not setting or setting.value is None:
            return default
        return str(setting.value).strip().lower() in {"1", "true", "on", "yes"}

    def set_bool(
        self,
        key: str,
        value: bool,
        *,
        description: Optional[str] = None,
        commit: bool = True,
    ) -> SystemSetting:
        return self.set_value(key, "1" if value else "0", description=description, commit=commit)


SettingsRepoInstance = SettingsRepo()
