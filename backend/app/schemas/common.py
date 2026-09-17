from pydantic import BaseModel, ConfigDict, computed_field


class Page[T](BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int
    page: int
    size: int

    @computed_field
    @property
    def pages(self) -> int:
        return (self.total + self.size - 1) // self.size if self.size else 0
