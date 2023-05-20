from dataclasses import dataclass, field
from typing import List, Optional

from adaptix import Retort, name_mapping


@dataclass
class Book:
    title: str
    sub_title: Optional[str] = None
    authors: List[str] = field(default_factory=list)


retort = Retort(
    recipe=[
        name_mapping(
            Book,
            omit_default=True,
        ),
    ]
)

book = Book(title='Fahrenheit 451')
assert retort.dump(book) == {'title': 'Fahrenheit 451'}
