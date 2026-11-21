"""Installe le récepteur depuis le Textport du portrait TouchDesigner."""

from pathlib import Path
from runpy import run_path

import yaml

HERE = Path(__file__).resolve().parent
CALLBACK = HERE / "touchdesigner_osc_callbacks.py"
APPARITION = HERE / "touchdesigner_apparition.py"


def dimension_rows(op):
    callback = run_path(str(CALLBACK))
    aliases = callback["ALIASES"]
    paths = {}
    for nom in callback["TRAITS"]:
        node = op(f"/trait_{nom}")
        if node is not None and getattr(node.par, "Intensite", None) is not None:
            paths[aliases.get(nom, nom)] = node.path
    channels = yaml.safe_load((HERE / "mapping_traits.yaml").read_text(encoding="utf-8"))["channels"]
    rows = [("dimension", "intensite", "composant")]
    rows.extend(
        (canal["dimension"], "", paths.get(canal["dimension"], "")) for canal in channels
    )
    return rows


def install(destination=HERE / "MindSight_Portrait_OSC.toe"):
    from td import baseCOMP, op, oscinDAT, project, tableDAT, textDAT

    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(f"Choisir un autre nom de destination. {destination} existe déjà.")

    rows = dimension_rows(op)
    if not any(chemin for _, _, chemin in rows[1:]):
        raise ValueError("Ouvrir le projet du portrait. Aucun trait avec un paramètre Intensite.")
    for chemin in ("/controles", "/composition/final"):
        if op(chemin) is None:
            raise ValueError(f"Ouvrir le projet du portrait. Opérateur introuvable {chemin}")
    finition = op("/finition")
    if finition is None or getattr(finition.par, "Force", None) is None:
        raise ValueError("Ouvrir le projet du portrait. Paramètre introuvable /finition.Force")
    apparition = op("/trait_impulsif/apparition")
    if apparition is not None and not isinstance(apparition, textDAT):
        raise TypeError(f"{apparition.path} doit être un Text DAT.")

    def get_or_create(parent, operator_type, name):
        node = parent.op(name)
        if node is None:
            return parent.create(operator_type, name, initialize=False)
        if not isinstance(node, operator_type):
            raise TypeError(f"{node.path} doit être de type {operator_type.__name__}.")
        return node

    root = get_or_create(op("/"), baseCOMP, "osc")
    receiver = get_or_create(root, oscinDAT, "osc_in")
    receiver.par.active = False
    callbacks = get_or_create(root, textDAT, "osc_in_callbacks")
    callbacks.text = CALLBACK.read_text(encoding="utf-8")
    callbacks.par.language = "python"
    dimensions = get_or_create(root, tableDAT, "dimensions")
    dimensions.clear()
    for row in rows:
        dimensions.appendRow(row)

    receiver.par.protocol = "msging"
    receiver.par.port = 9000
    receiver.par.localaddress = "127.0.0.1"
    receiver.par.addscope = "*"
    receiver.par.splitmessage = True
    receiver.par.clamp = True
    receiver.par.maxlines = 100
    receiver.par.callbacks = callbacks.path
    receiver.par.executeloc = "callbacks"
    if apparition is not None:
        apparition.text = APPARITION.read_text(encoding="utf-8")
    receiver.par.active = True
    project.save(destination.as_posix(), saveExternalToxs=False)
    print(f"Portrait OSC enregistré dans {destination}")


if __name__ == "__main__":
    install()
