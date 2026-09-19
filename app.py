from __future__ import annotations

import io
import os
import uuid
from collections import defaultdict
from datetime import date, datetime
from statistics import mean

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from PIL import Image, ImageOps
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
IMAGE_BUCKET = os.getenv("SUPABASE_IMAGE_BUCKET", "bento-images").strip() or "bento-images"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

_supabase: Client | None = None


def supabase() -> Client:
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL og SUPABASE_PUBLISHABLE_KEY mangler. Kopiér .env.example til .env og udfyld dem."
            )
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase


def average(values):
    nums = [float(value) for value in values if value is not None]
    return mean(nums) if nums else None


def bento_average(bento):
    return average(rating.get("rating") for rating in bento.get("bento_ratings", []))


def component_average(bento_component):
    return average(rating.get("rating") for rating in bento_component.get("component_ratings", []))


def image_url(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return supabase().storage.from_(IMAGE_BUCKET).get_public_url(path)
    except Exception:
        return None


@app.template_filter("date_da")
def date_da(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return value
    months = [
        "jan.", "feb.", "mar.", "apr.", "maj", "jun.",
        "jul.", "aug.", "sep.", "okt.", "nov.", "dec.",
    ]
    return f"{value.day}. {months[value.month - 1]} {value.year}"


@app.template_filter("rating")
def rating_da(value):
    if value is None:
        return "Ikke rated endnu"
    return f"{float(value):.1f}".replace(".", ",") + " ★"


@app.context_processor
def shared_template_helpers():
    return {
        "bento_average": bento_average,
        "component_average": component_average,
        "image_url": image_url,
        "rating_options": [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5],
    }


def fetch_bentos():
    response = (
        supabase()
        .table("bentos")
        .select(
            "*,"
            "bento_components(id,component:components(id,name),"
            "component_ratings(id,rater_name,rating,comment)),"
            "bento_ratings(id,rater_name,rating,comment)"
        )
        .order("bento_date", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def fetch_bento(bento_id: int):
    response = (
        supabase()
        .table("bentos")
        .select(
            "*,"
            "bento_components(id,component:components(id,name),"
            "component_ratings(id,rater_name,rating,comment)),"
            "bento_ratings(id,rater_name,rating,comment)"
        )
        .eq("id", bento_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def build_analytics(bentos):
    rated_bentos = [b for b in bentos if bento_average(b) is not None]
    overall = average(bento_average(b) for b in rated_bentos)
    favorite_count = sum(bool(b.get("is_favorite")) for b in bentos)
    high_pct = (
        100 * sum(bento_average(b) >= 4.5 for b in rated_bentos) / len(rated_bentos)
        if rated_bentos
        else None
    )

    component_map = defaultdict(lambda: {"name": "", "ratings": [], "appearances": 0})
    for bento in bentos:
        for bc in bento.get("bento_components", []):
            component = bc.get("component") or {}
            component_id = component.get("id")
            if component_id is None:
                continue
            item = component_map[component_id]
            item["name"] = component.get("name", "")
            item["appearances"] += 1
            item["ratings"].extend(
                float(r["rating"]) for r in bc.get("component_ratings", []) if r.get("rating") is not None
            )

    components = []
    for item in component_map.values():
        components.append({**item, "average": average(item["ratings"])})

    ranked = sorted(
        [c for c in components if c["average"] is not None],
        key=lambda c: (-c["average"], -len(c["ratings"]), -c["appearances"], c["name"].lower()),
    )
    most_used = sorted(components, key=lambda c: (-c["appearances"], c["name"].lower()))
    best = max(rated_bentos, key=bento_average, default=None)

    chronological = sorted(
        rated_bentos,
        key=lambda b: (b.get("bento_date", ""), int(b.get("id", 0))),
    )
    trend = None
    if len(chronological) >= 10:
        latest = [bento_average(b) for b in chronological[-5:]]
        previous = [bento_average(b) for b in chronological[-10:-5]]
        trend = average(latest) - average(previous)

    return {
        "count": len(bentos),
        "overall": overall,
        "favorite_count": favorite_count,
        "high_pct": high_pct,
        "ranked_components": ranked,
        "most_used_components": most_used,
        "best_bento": best,
        "trend": trend,
    }


def get_or_create_component(name: str):
    clean_name = " ".join(name.split()).strip()
    if not clean_name:
        raise ValueError("Tomt komponentnavn")

    existing = supabase().table("components").select("id,name").ilike("name", clean_name).limit(1).execute()
    if existing.data:
        return existing.data[0]

    try:
        created = supabase().table("components").insert({"name": clean_name}).execute()
        if created.data:
            return created.data[0]
    except Exception:
        pass

    retry = supabase().table("components").select("id,name").ilike("name", clean_name).limit(1).execute()
    if retry.data:
        return retry.data[0]
    raise RuntimeError(f"Kunne ikke oprette komponenten {clean_name!r}")


def prepare_image(upload):
    if not upload or not upload.filename:
        return None
    if upload.mimetype not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Billedet skal være JPEG, PNG eller WebP.")

    original = upload.read(MAX_IMAGE_BYTES + 1)
    if len(original) > MAX_IMAGE_BYTES:
        raise ValueError("Billedet må højst fylde 5 MB.")

    try:
        image = Image.open(io.BytesIO(original))
        image = ImageOps.exif_transpose(image)
        image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)

        has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
        output = io.BytesIO()
        if has_alpha:
            image.convert("RGBA").save(output, format="WEBP", quality=86, method=6)
            return output.getvalue(), "image/webp", "webp"

        image.convert("RGB").save(output, format="JPEG", quality=86, optimize=True)
        return output.getvalue(), "image/jpeg", "jpg"
    except Exception as exc:
        raise ValueError("Billedet kunne ikke læses.") from exc


@app.route("/")
def today():
    try:
        bentos = fetch_bentos()
    except Exception as exc:
        app.logger.exception("Could not load bentos")
        return render_template("today.html", bento=None, setup_error=str(exc), active_page="today")

    bento = bentos[0] if bentos else None
    return render_template("today.html", bento=bento, active_page="today")


@app.route("/bento/<int:bento_id>")
def bento_detail(bento_id):
    try:
        bento = fetch_bento(bento_id)
    except Exception as exc:
        app.logger.exception("Could not load bento")
        flash(f"Kunne ikke hente bentoen: {exc}", "error")
        return redirect(url_for("today"))
    if not bento:
        flash("Bentoen findes ikke længere.", "error")
        return redirect(url_for("today"))
    return render_template("today.html", bento=bento, active_page="today")


@app.post("/bento/<int:bento_id>/favorite")
def toggle_favorite(bento_id):
    bento = fetch_bento(bento_id)
    if not bento:
        flash("Bentoen findes ikke.", "error")
        return redirect(url_for("today"))
    try:
        supabase().table("bentos").update({"is_favorite": not bool(bento.get("is_favorite"))}).eq("id", bento_id).execute()
        flash("Favoritstatus opdateret.", "success")
    except Exception:
        app.logger.exception("Could not update favorite")
        flash("Kunne ikke ændre favoritstatus.", "error")
    return redirect(url_for("bento_detail", bento_id=bento_id))


@app.post("/bento/<int:bento_id>/rate")
def save_rating(bento_id):
    bento = fetch_bento(bento_id)
    if not bento:
        flash("Bentoen findes ikke.", "error")
        return redirect(url_for("today"))

    rater = " ".join(request.form.get("rater", "").split()).strip()
    comment = request.form.get("comment", "").strip() or None
    try:
        overall = float(request.form.get("overall", ""))
    except ValueError:
        overall = 0

    if not rater or not (1 <= overall <= 5) or overall * 2 != int(overall * 2):
        flash("Udfyld navn og en gyldig rating fra 1 til 5.", "error")
        return redirect(url_for("bento_detail", bento_id=bento_id))

    try:
        component_values = {}
        for bc in bento.get("bento_components", []):
            raw = request.form.get(f"component_{bc['id']}", "")
            component_rating = float(raw)
            if not (1 <= component_rating <= 5) or component_rating * 2 != int(component_rating * 2):
                raise ValueError("Ugyldig komponent-rating")
            component_values[bc["id"]] = component_rating

        existing = next(
            (r for r in bento.get("bento_ratings", []) if r.get("rater_name", "").casefold() == rater.casefold()),
            None,
        )
        payload = {"rater_name": rater, "rating": overall, "comment": comment}
        if existing:
            supabase().table("bento_ratings").update(payload).eq("id", existing["id"]).execute()
        else:
            supabase().table("bento_ratings").insert({"bento_id": bento_id, **payload}).execute()

        for bc in bento.get("bento_components", []):
            component_rating = component_values[bc["id"]]
            old = next(
                (r for r in bc.get("component_ratings", []) if r.get("rater_name", "").casefold() == rater.casefold()),
                None,
            )
            component_payload = {"rater_name": rater, "rating": component_rating}
            if old:
                supabase().table("component_ratings").update(component_payload).eq("id", old["id"]).execute()
            else:
                supabase().table("component_ratings").insert(
                    {"bento_component_id": bc["id"], **component_payload}
                ).execute()

        flash("Rating gemt.", "success")
    except Exception:
        app.logger.exception("Could not save rating")
        flash("Kunne ikke gemme hele ratingen. Prøv igen.", "error")

    return redirect(url_for("bento_detail", bento_id=bento_id))


@app.route("/new", methods=["GET", "POST"])
def new_bento():
    remake = None
    remake_id = request.args.get("remake", type=int)
    if remake_id:
        try:
            remake = fetch_bento(remake_id)
        except Exception:
            app.logger.exception("Could not load remake bento")

    if request.method == "POST":
        name = " ".join(request.form.get("name", "").split()).strip()
        bento_date = request.form.get("date", "").strip()
        comment = request.form.get("comment", "").strip() or None
        components = []
        seen = set()
        for value in request.form.getlist("components"):
            clean = " ".join(value.split()).strip()
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                components.append(clean)

        if not name:
            flash("Bentoen skal have et navn.", "error")
        elif not components:
            flash("Tilføj mindst én komponent.", "error")
        else:
            try:
                date.fromisoformat(bento_date)
            except ValueError:
                flash("Vælg en gyldig dato.", "error")
            else:
                try:
                    created = (
                        supabase()
                        .table("bentos")
                        .insert({"name": name, "bento_date": bento_date, "comment": comment})
                        .execute()
                    )
                    bento = created.data[0]
                    bento_id = bento["id"]

                    component_failures = False
                    for component_name in components:
                        try:
                            component = get_or_create_component(component_name)
                            supabase().table("bento_components").insert(
                                {"bento_id": bento_id, "component_id": component["id"]}
                            ).execute()
                        except Exception:
                            app.logger.exception("Could not add component")
                            component_failures = True

                    image_failure = None
                    upload = request.files.get("image")
                    if upload and upload.filename:
                        try:
                            file_bytes, mime, extension = prepare_image(upload)
                            path = f"bentos/{bento_id}/{uuid.uuid4()}.{extension}"
                            supabase().storage.from_(IMAGE_BUCKET).upload(
                                path=path,
                                file=io.BytesIO(file_bytes),
                                file_options={"content-type": mime, "upsert": "false"},
                            )
                            supabase().table("bentos").update({"image_path": path}).eq("id", bento_id).execute()
                        except Exception as exc:
                            app.logger.exception("Could not upload bento image")
                            image_failure = str(exc)

                    if component_failures:
                        flash("Bentoen blev oprettet, men nogle komponenter kunne ikke gemmes.", "error")
                    elif image_failure:
                        flash(f"Bentoen blev oprettet uden billede. {image_failure}", "error")
                    else:
                        flash("Bento oprettet!", "success")
                    return redirect(url_for("bento_detail", bento_id=bento_id))
                except Exception:
                    app.logger.exception("Could not create bento")
                    flash("Kunne ikke oprette bentoen.", "error")

    seed_components = []
    seed_name = ""
    if remake:
        seed_name = remake.get("name", "")
        seed_components = [
            (bc.get("component") or {}).get("name", "")
            for bc in remake.get("bento_components", [])
            if (bc.get("component") or {}).get("name")
        ]

    return render_template(
        "new.html",
        active_page="new",
        seed_name=seed_name,
        seed_components=seed_components,
        today_iso=date.today().isoformat(),
        is_remake=bool(remake),
    )


@app.route("/history")
def history():
    try:
        bentos = fetch_bentos()
        bentos.sort(key=lambda b: (not bool(b.get("is_favorite")), b.get("bento_date", "")), reverse=False)
        # Favorites first; within each group newest first.
        bentos = sorted(bentos, key=lambda b: b.get("bento_date", ""), reverse=True)
        bentos = sorted(bentos, key=lambda b: not bool(b.get("is_favorite")))
    except Exception as exc:
        app.logger.exception("Could not load history")
        bentos = []
        flash(f"Kunne ikke hente historikken: {exc}", "error")
    return render_template("history.html", bentos=bentos, active_page="history")


@app.route("/analytics")
def analytics():
    try:
        bentos = fetch_bentos()
        data = build_analytics(bentos)
    except Exception as exc:
        app.logger.exception("Could not build analytics")
        data = build_analytics([])
        flash(f"Kunne ikke hente analytics: {exc}", "error")
    return render_template("analytics.html", data=data, active_page="analytics")


@app.errorhandler(413)
def too_large(_error):
    flash("Uploaden er for stor. Vælg et billede under 5 MB.", "error")
    return redirect(request.referrer or url_for("new_bento"))


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1")
