"""Gera a animação da cobrinha que come o gráfico de contribuições e cresce.

Uso: python scripts/cobrinha.py PASTA_DE_SAIDA
Precisa de GITHUB_TOKEN (no Actions, o token automático já serve).

Regras da cobra:
- anda só dentro das 7 linhas da grade;
- começa com 1 quadrado e cresce meio quadrado a cada dia com contribuição que come;
- nunca passa por cima do próprio corpo, como no jogo de verdade.

O planejador simula o corpo passo a passo: uma casa ocupada só fica livre quando a cauda já
saiu dela com folga. Antes de ir até uma contribuição, ele confere se a cobra ainda terá espaço
para sair de lá; se nenhum alvo for seguro, dá um passo para a região mais livre. No fim, um
verificador independente refaz a animação e falha se houver qualquer colisão.

O corpo é um traço grosso sobre o caminho completo; a parte visível é controlada por
stroke-dasharray/stroke-dashoffset animados em CSS.
"""
import json
import os
import random
import sys
import urllib.request
from collections import deque
from pathlib import Path

USUARIO = os.environ.get("GITHUB_REPOSITORY_OWNER", "DevRGS")
CELULA, ESPACO, MARGEM = 11, 3, 6
PASSO_PX = CELULA + ESPACO
TAMANHO_INICIAL = 1.0  # em quadrados
CRESCIMENTO = 0.5      # quadrados ganhos por dia comido

TEMAS = {
    "github-snake.svg": {
        "niveis": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
        "cobra": "#7c3aed", "olho": "#ffffff",
    },
    "github-snake-dark.svg": {
        "niveis": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
        "cobra": "#a78bfa", "olho": "#0d1117",
    },
}
NIVEL = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def buscar_grade() -> dict:
    consulta = """query($login: String!) { user(login: $login) { contributionsCollection {
      contributionCalendar { weeks { contributionDays { weekday contributionLevel } } } } } }"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": consulta, "variables": {"login": USUARIO}}).encode(),
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "User-Agent": "perfil-readme"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        dados = json.load(resp)
    if "errors" in dados:
        sys.exit(f"Erro na API do GitHub: {dados['errors']}")
    semanas = dados["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return {(x, d["weekday"]): NIVEL[d["contributionLevel"]]
            for x, semana in enumerate(semanas) for d in semana["contributionDays"]}


def vizinhos(casa: tuple):
    x, y = casa
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def tamanho_em(t: float, passos_comida: list) -> float:
    """Comprimento da cobra (em quadrados) no instante t, medido em passos.
    Cada comida faz a cobra crescer ao longo do passo seguinte (a cauda fica parada)."""
    return TAMANHO_INICIAL + CRESCIMENTO * sum(min(max(t - e, 0), 1) for e in passos_comida)


# ---------- Planejamento da rota ----------

class Planejador:
    def __init__(self, grade: dict, estrategia: int = 0):
        self.grade = grade
        self.estrategia = estrategia
        self.sorteio = random.Random(estrategia)
        self.alvos = {c for c, n in grade.items() if n > 0}
        inicio = min(grade)
        self.rota = [inicio]
        self.ultimo = {inicio: 0}  # última vez (índice do passo) em que a cabeça esteve em cada casa
        self.comidas = []          # (índice do passo, casa)
        if inicio in self.alvos:
            self.comer(inicio)

    def tamanho(self) -> float:
        # Conta todas as comidas como já digeridas: é um limite por cima, então é seguro.
        return TAMANHO_INICIAL + CRESCIMENTO * len(self.comidas)

    def comer(self, casa) -> None:
        self.alvos.discard(casa)
        self.comidas.append((len(self.rota) - 1, casa))

    @staticmethod
    def livre(grade, ultimo, casa, chegada, tamanho) -> bool:
        """A casa está livre se a cauda saiu dela pelo menos 1 quadrado antes da cabeça chegar."""
        if casa not in grade:
            return False
        visto = ultimo.get(casa)
        return visto is None or visto <= chegada - tamanho - 1

    def busca(self, ultimo, cabeca, t, tamanho):
        """BFS respeitando o corpo, que vai liberando casas conforme a cobra anda."""
        anterior, dist = {cabeca: None}, {cabeca: 0}
        fila = deque([cabeca])
        while fila:
            atual = fila.popleft()
            for viz in vizinhos(atual):
                if viz not in anterior and self.livre(self.grade, ultimo, viz, t + dist[atual] + 1, tamanho):
                    anterior[viz] = atual
                    dist[viz] = dist[atual] + 1
                    fila.append(viz)
        return anterior, dist

    def espaco_livre(self, ultimo, cabeca, t, tamanho) -> int:
        return len(self.busca(ultimo, cabeca, t, tamanho)[1]) - 1

    def seguro(self, trajeto: list, tamanho_final: float) -> bool:
        """Depois de comer no fim do trajeto, a cobra ainda consegue se mover sem ficar presa?"""
        if len(self.alvos) == 1:
            return True  # último alvo: não precisa sair de lá
        ultimo = dict(self.ultimo)
        t = len(self.rota) - 1
        for i, casa in enumerate(trajeto, start=1):
            ultimo[casa] = t + i
        return self.espaco_livre(ultimo, trajeto[-1], t + len(trajeto), tamanho_final) >= tamanho_final + 3

    def andar(self, trajeto: list) -> None:
        for casa in trajeto:
            self.rota.append(casa)
            self.ultimo[casa] = len(self.rota) - 1

    def desempate(self, casa):
        """Critério entre alvos à mesma distância; cada estratégia testa um diferente."""
        x, y = casa
        if self.estrategia == 0:
            return (x, y)                      # da esquerda para a direita
        if self.estrategia == 1:
            return (-x, y)                     # da direita para a esquerda
        if self.estrategia == 2:               # prefere bordas e cantos (deixa o meio livre)
            return (sum(v in self.grade for v in vizinhos(casa)), x, y)
        if self.estrategia == 3:               # prefere alvos com vizinhos que também são alvos
            return (-sum(v in self.alvos for v in vizinhos(casa)), x, y)
        return self.sorteio.random()           # demais: desempate aleatório reprodutível

    def planejar(self):
        limite = 40 * len(self.grade)
        while self.alvos and len(self.rota) < limite:
            cabeca, t, tamanho = self.rota[-1], len(self.rota) - 1, self.tamanho()
            anterior, dist = self.busca(self.ultimo, cabeca, t, tamanho)
            escolhido = None
            for alvo in sorted((c for c in self.alvos if c in dist), key=lambda c: (dist[c], self.desempate(c))):
                trajeto, atual = [], alvo
                while atual != cabeca:
                    trajeto.append(atual)
                    atual = anterior[atual]
                trajeto.reverse()
                if self.seguro(trajeto, tamanho + CRESCIMENTO):
                    escolhido = trajeto
                    break
            if escolhido:
                self.andar(escolhido)
                self.comer(escolhido[-1])
                continue
            # Nenhum alvo seguro agora: um passo para onde houver mais espaço, esperando a cauda liberar.
            opcoes = []
            for viz in vizinhos(cabeca):
                if self.livre(self.grade, self.ultimo, viz, t + 1, tamanho):
                    ultimo = dict(self.ultimo)
                    ultimo[viz] = t + 1
                    opcoes.append((self.espaco_livre(ultimo, viz, t + 1, tamanho), viz))
            if not opcoes:
                break  # encurralada (não deve acontecer com a checagem de segurança)
            passo = max(opcoes)[1]
            self.andar([passo])
            if passo in self.alvos:
                self.comer(passo)
        return self.rota, self.comidas


def melhor_rota(grade: dict, estrategias: int = 10):
    """Testa várias estratégias e fica com a que come mais dias; no empate, a de menos passos."""
    total = sum(1 for n in grade.values() if n > 0)
    melhor = None
    for e in range(estrategias):
        rota, comidas = Planejador(grade, e).planejar()
        nota = (len(comidas), -len(rota))
        if melhor is None or nota > melhor[0]:
            melhor = (nota, rota, comidas)
        if len(comidas) == total and e >= 3:
            break  # já comeu tudo e testou as estratégias principais
    return melhor[1], melhor[2]


def verificar(grade: dict, rota: list, comidas: list) -> None:
    """Refaz a animação passo a passo e garante que a cabeça nunca encosta no corpo."""
    passos_comida = [i for i, _ in comidas]
    for t in range(1, len(rota)):
        if rota[t] not in grade or rota[t] not in vizinhos(rota[t - 1]):
            raise SystemExit(f"Movimento inválido no passo {t}: {rota[t - 1]} -> {rota[t]}")
        limite = t - tamanho_em(t, passos_comida) - 1
        for j in range(t):
            if rota[j] == rota[t] and j > limite + 1e-9:
                raise SystemExit(f"Colisão no passo {t}: a cabeça voltou à casa {rota[t]} do passo {j}")


# ---------- Desenho ----------

def centro(casa: tuple) -> tuple:
    x, y = casa
    return MARGEM + x * PASSO_PX + CELULA / 2, MARGEM + y * PASSO_PX + CELULA / 2


def gerar_svg(grade: dict, rota: list, comidas: list, tema: dict) -> str:
    colunas = max(x for x, _ in grade) + 1
    largura = MARGEM * 2 + colunas * PASSO_PX - ESPACO
    altura = MARGEM * 2 + 7 * PASSO_PX - ESPACO
    passos = len(rota) - 1
    dur_passo = min(0.15, max(0.06, 50 / max(passos, 1)))
    pausa = 2.5
    total = passos * dur_passo + pausa
    pct = lambda t: f"{min(t / total * 100, 100):.4f}%"

    passos_comida = [i for i, _ in comidas]
    comprimento = lambda t: PASSO_PX * tamanho_em(t / dur_passo, passos_comida)
    cabeca = lambda t: min(t / dur_passo, passos) * PASSO_PX

    fim_mov = passos * dur_passo
    marcos = sorted({0.0, fim_mov, total} | {e * dur_passo for e in passos_comida}
                    | {min((e + 1) * dur_passo, fim_mov) for e in passos_comida})
    grande = (passos + 10) * PASSO_PX
    quadros_corpo = " ".join(
        f"{pct(t)}{{stroke-dasharray:{comprimento(t):.2f} {grande};stroke-dashoffset:{comprimento(t) - cabeca(t):.2f}}}"
        for t in marcos)

    quadros_olho = " ".join(
        f"{pct(i * dur_passo)}{{transform:translate({centro(c)[0]:.1f}px,{centro(c)[1]:.1f}px)}}"
        for i, c in enumerate(rota))
    fim = centro(rota[-1])
    quadros_olho += f" 100%{{transform:translate({fim[0]:.1f}px,{fim[1]:.1f}px)}}"

    niveis = tema["niveis"]
    css = [
        ".c{shape-rendering:geometricPrecision;rx:2;ry:2}",
        f"#corpo{{fill:none;stroke:{tema['cobra']};stroke-width:{CELULA - 1};stroke-linecap:round;stroke-linejoin:round;"
        f"animation:corpo {total:.2f}s linear infinite}}",
        f"@keyframes corpo{{{quadros_corpo}}}",
        f"#olho{{fill:{tema['olho']};animation:olho {total:.2f}s linear infinite}}",
        f"@keyframes olho{{{quadros_olho}}}",
    ]
    comida_em = {casa: i * dur_passo for i, casa in comidas}
    rects = []
    for (x, y), nivel in sorted(grade.items()):
        px, py = MARGEM + x * PASSO_PX, MARGEM + y * PASSO_PX
        atributos = f'class="c" x="{px}" y="{py}" width="{CELULA}" height="{CELULA}" fill="{niveis[nivel]}"'
        if (x, y) in comida_em:
            nome = f"e{x}_{y}"
            t = comida_em[(x, y)]
            css.append(f"@keyframes {nome}{{0%,{pct(t)}{{fill:{niveis[nivel]}}}"
                       f"{pct(t + 0.001)},100%{{fill:{niveis[0]}}}}}")
            atributos += f' style="animation:{nome} {total:.2f}s linear infinite"'
        rects.append(f"<rect {atributos}/>")

    d = "M" + " L".join(f"{cx:.1f} {cy:.1f}" for cx, cy in map(centro, rota))
    if passos == 0:  # sem contribuições: cobra parada no canto
        css = css[:1]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" width="{largura}" height="{altura}">'
            f"<style>{''.join(css)}</style>{''.join(rects)}"
            f'<path id="corpo" d="{d}"/><circle id="olho" cx="0" cy="0" r="2"/></svg>')


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"Uso: python {sys.argv[0]} PASTA_DE_SAIDA")
    saida = Path(sys.argv[1])
    saida.mkdir(parents=True, exist_ok=True)
    grade = buscar_grade()
    rota, comidas = melhor_rota(grade)
    verificar(grade, rota, comidas)
    total_alvos = sum(1 for n in grade.values() if n > 0)
    for arquivo, tema in TEMAS.items():
        (saida / arquivo).write_text(gerar_svg(grade, rota, comidas, tema), encoding="utf-8")
    print(f"{len(comidas)}/{total_alvos} dias comidos em {len(rota) - 1} passos, sem colisões. "
          f"Tamanho final: {tamanho_em(len(rota), [i for i, _ in comidas]):.1f} quadrados.")


if __name__ == "__main__":
    main()
