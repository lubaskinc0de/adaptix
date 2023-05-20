from abc import ABC, abstractmethod
from typing import Mapping, Sequence, TypeVar, Union

from adaptix._internal.provider.model.crown_definitions import (
    DictExtraPolicy,
    Extractor,
    ExtraForbid,
    ExtraKwargs,
    ExtraSkip,
    InpExtraMove,
    InputNameLayoutRequest,
    LeafInpCrown,
    LeafOutCrown,
    OutExtraMove,
    OutputNameLayoutRequest,
    Saturator,
    Sieve,
)

from ...common import VarTuple
from ...essential import Mediator

T = TypeVar('T')


ExtraIn = Union[ExtraSkip, str, Sequence[str], ExtraForbid, ExtraKwargs, Saturator]
ExtraOut = Union[ExtraSkip, str, Sequence[str], Extractor]

Key = Union[str, int]
Path = VarTuple[Key]
PathsTo = Mapping[Path, T]


class ExtraMoveMaker(ABC):
    @abstractmethod
    def make_inp_extra_move(
        self,
        mediator: Mediator,
        request: InputNameLayoutRequest,
    ) -> InpExtraMove:
        ...

    @abstractmethod
    def make_out_extra_move(
        self,
        mediator: Mediator,
        request: OutputNameLayoutRequest,
    ) -> OutExtraMove:
        ...


class StructureMaker(ABC):
    @abstractmethod
    def make_inp_structure(
        self,
        mediator: Mediator,
        request: InputNameLayoutRequest,
        extra_move: InpExtraMove,
    ) -> PathsTo[LeafInpCrown]:
        ...

    @abstractmethod
    def make_out_structure(
        self,
        mediator: Mediator,
        request: OutputNameLayoutRequest,
        extra_move: OutExtraMove,
    ) -> PathsTo[LeafOutCrown]:
        ...


class SievesMaker(ABC):
    @abstractmethod
    def make_sieves(
        self,
        mediator: Mediator,
        request: OutputNameLayoutRequest,
        paths_to_leaves: PathsTo[LeafOutCrown],
    ) -> PathsTo[Sieve]:
        ...


class ExtraPoliciesMaker(ABC):
    @abstractmethod
    def make_extra_policies(
        self,
        mediator: Mediator,
        request: InputNameLayoutRequest,
        paths_to_leaves: PathsTo[LeafInpCrown],
    ) -> PathsTo[DictExtraPolicy]:
        ...
