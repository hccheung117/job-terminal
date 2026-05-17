from sqlmodel import Field, SQLModel


class Keyword(SQLModel, table=True):
    __tablename__ = "keywords"

    id: int | None = Field(default=None, primary_key=True)
    group: str = Field(index=True)
    keyword: str
