from sqlmodel import Field, SQLModel


class SpiderKeyword(SQLModel, table=True):
    __tablename__ = "spider_keywords"

    id: int | None = Field(default=None, primary_key=True)
    group: str = Field(index=True)
    keyword: str
