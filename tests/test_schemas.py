
import pytest
from pydantic import ValidationError

from app.schemas import ResultadoEvaluacion


def test_resultado_evaluacion_acepta_categoria_valida():
    resultado = ResultadoEvaluacion(
        evaluacion="Bien",
        mejora="Podría ampliar la explicación.",
    )

    assert resultado.evaluacion == "Bien"
    assert resultado.mejora == "Podría ampliar la explicación."


def test_resultado_evaluacion_rechaza_categoria_invalida():
    with pytest.raises(ValidationError):
        ResultadoEvaluacion(
            evaluacion="Excelente",
            mejora="Sin mejoras.",
        )
