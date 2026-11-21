"""Installe le récepteur depuis le Textport du portrait TouchDesigner."""

from pathlib import Path
from runpy import run_path

import yaml

HERE = Path(__file__).resolve().parent
CALLBACK = HERE / "touchdesigner_osc_callbacks.py"
APPARITION = HERE / "touchdesigner_apparition.py"


def dimension_rows():
    callback = run_path(str(CALLBACK))
    aliases = callback["ALIASES"]
    paths = {aliases.get(nom, nom): f"/trait_{nom}" for nom in callback["TRAITS"]}
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

    rows = dimension_rows()
    expected = [
        (chemin, "Intensite") for _, _, chemin in rows[1:] if chemin
    ] + [("/trait_impulsif", "Boucle"), ("/finition", "Force")]
    for chemin, nom in expected:
        node = op(chemin)
        if node is None or getattr(node.par, nom, None) is None:
            raise ValueError(f"Ouvrir le projet du portrait. Paramètre introuvable {chemin}.{nom}")
    for chemin in ("/trait_impulsif/apparition", "/controles", "/composition/final"):
        if op(chemin) is None:
            raise ValueError(f"Ouvrir le projet du portrait. Opérateur introuvable {chemin}")
    apparition = op("/trait_impulsif/apparition")
    if not isinstance(apparition, textDAT):
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
    apparition.text = APPARITION.read_text(encoding="utf-8")
    receiver.par.active = True
    project.save(destination.as_posix(), saveExternalToxs=False)
    print(f"Portrait OSC enregistré dans {destination}")


if __name__ == "__main__":
    install()
