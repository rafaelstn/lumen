"""Módulo de consumo de APIs pagas: audit trail persistente, saldo por controle interno
e histórico de consultas. Transversal aos módulos 01 e 02.

Todo valor monetário é inteiro em CENTAVOS (nunca float). O custo de cada operação é
gravado no momento (snapshot do preço unitário), garantindo que mudanças futuras de preço
não reescrevam o histórico. Cada operação paga gera um ConsultaLog atômico junto da escrita.
"""
