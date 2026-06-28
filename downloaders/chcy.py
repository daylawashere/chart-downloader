from main import AnsiColors

MUS_START_PADDING = 9 #Fuckffmpeg

JACKET_SIZE = [740, 740]

locale_keys = {
    "name": "cc_all",
    "name_archive": "cc",
    "name_offshoot": "cc_o",
    "chart_id_format": "cc_chart_id_format",
    "chart_id_prompt": "chart_id",
    "invalid_chart_id": "invalid_chart_id",
    "choose_instance": "choose_instance",
}
arguments = {
    "instance": {
        "required": True,
        "prompt": "choose_instance",
        "choices": ["chcy", "chcy-o"],
        "choices_names": ["name_archive", "name_offshoot"],
    },
    "chart_id": {
        "required": True,
        "prompt": ["chart_id_prompt", "chart_id_format"],
        "invalid": "invalid_chart_id",
        "validate": [
            "arg.startswith('chcy-')",
            "len(arg) == 28",
            "arg.removeprefix('chcy-').isalnum()",
        ],
    },
}

from pathlib import Path

def exporter(locale, out_path: Path, instance: str, chart_id: str):
    import json
    from sonolus_converters import usc, LevelData, pjsk, sus
    import requests
    from helpers.file_downloader import download_file
    from helpers.file_type import detect_image, detect_audio
    import shutil
    import gzip
    import base64
    from pydub import AudioSegment
    from PIL import Image

    server_url = (
        "https://cc.milkbun.org" if instance == "chcy" else "https://chart-cyanvas.com"
    )

    print(AnsiColors.apply_foreground(locale.fetching, AnsiColors.BLUE))
    url = f"{server_url}/sonolus/levels/{chart_id}"
    response = requests.get(url)
    if response.status_code == 200:
        try:
            data = response.json()
        except json.JSONDecodeError:
            return locale.invalid_chart_id  # returns 200 for not found... but html
    else:
        if response.status_code == 404:
            return locale.invalid_chart_id
        response.raise_for_status()
        return locale.unknown_error  # in case it's something like 201
    item = data["item"]
    print(f"[{item['rating']}] {item['title']}")
    print(item["artists"])
    print(item["author"])
    del item["engine"]

    server_out_path = out_path / instance
    level_out_path = server_out_path / chart_id
    level_out_path.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(level_out_path)
    level_out_path.mkdir(parents=True, exist_ok=True)
    with open(level_out_path / "level.json", "w", encoding="utf8") as f:
        json.dump(item, f)

    print(AnsiColors.apply_foreground(locale.downloading, AnsiColors.BLUE))

    if "data" in item:
        print("Score...")
        data_url = item["data"]["url"]
        if data_url.startswith("/"):
            data_url = server_url + data_url
        download_file(data_url, level_out_path / "ChCyLevelData.json.gz")
    else:
        raise KeyError("Missing score file.")

    if "bgm" in item:
        print("Music...")
        bgm_url = item["bgm"]["url"]
        if bgm_url.startswith("/"):
            bgm_url = server_url + bgm_url

        music_path = level_out_path / "music"
        download_file(bgm_url, music_path)

        mus_ext = detect_audio(music_path)
        if mus_ext != "unknown":
            print("adding filler secs to audio file")
            new_path = music_path.with_suffix(f".{mus_ext}")
            music_path.rename(new_path)
            mus_no_padding = AudioSegment.from_file(new_path)
            padding = AudioSegment.silent(duration=MUS_START_PADDING*1000)
            output_mus = padding + mus_no_padding
            output_mus.export(new_path, format="mp3")

    if "preview" in item:
        print("Preview...")
        preview_url = item["preview"]["url"]
        if preview_url.startswith("/"):
            preview_url = server_url + preview_url

        preview_path = level_out_path / "preview"
        download_file(preview_url, preview_path)
        ext = detect_audio(preview_path)
        if ext != "unknown":
            new_path = preview_path.with_suffix(f".{ext}")
            preview_path.rename(new_path)

    if "cover" in item:
        print("Jacket...")
        cover_url = item["cover"]["url"]
        if cover_url.startswith("/"):
            cover_url = server_url + cover_url

        jacket_path = level_out_path / "jacket"
        download_file(cover_url, jacket_path)

        jkt_ext = detect_image(jacket_path)
        if jkt_ext != "unknown":
            new_path = jacket_path.with_suffix(f".{jkt_ext}")
            jacket_path.rename(new_path)
            print(jacket_path)
            resized_jkt = Image.open(new_path)
            print("resizing")
            resized_jkt = resized_jkt.resize(JACKET_SIZE)
            resized_jkt.save(new_path)


    print(AnsiColors.apply_foreground(locale.converting, AnsiColors.BLUE))
    with open(level_out_path / "ChCyLevelData.json.gz", "rb") as f:
        score = LevelData.chart_cyanvas.load(f)
        music_offset = score.metadata.waveoffset + (0.03 if mus_ext == "mp3" else 0) 
    usc.export(level_out_path / "score.usc", score)
    
    print("attempting sus conversion")
    with open(level_out_path / "score.usc", "r") as f:
        score = usc.load(f)
    sus.export(level_out_path / "score.sus", score)
    
    with open(level_out_path / "score.sus", "r") as f:
        score = sus.load(f)
    pjsk.export(level_out_path / "score.json.gz", score, 1234567)
    
    with open(level_out_path / "score.json", "w") as f:
        score_path = (level_out_path / "score.json.gz")
        score = gzip.decompress(base64.b64decode(score_path.read_bytes()))
        f.write(score.decode("utf-8"))
        
    manifest = level_to_manifest(item, chart_id, jkt_ext, music_offset)
        
    with open(level_out_path / "manifest.json", "w", encoding="utf8") as f:
        json.dump(manifest, f)
        
    shutil.make_archive(level_out_path, 'zip', level_out_path)
    print(f"Exporting song archive...")
    shutil.rmtree(level_out_path)
        
    return True

def level_to_manifest(chart_data, id, jkt_ext, waveoffset):
    
    m = chart_data
    
    m["formatVersion"] = 1
    m["id"] = id
    m["scoretitle"] = f"{m["title"]}"
    m["musicDifficultyType"] = "easy" # I can't really guess lmao ill see later if i can read diff from tags or smt
    m["audioFileName"] = "music.mp3"
    m["jacketFileName"] = f"jacket.{jkt_ext}"
    m["scoreFileName"] = "score.json"
    m["lyricist"] = "-"
    m["composer"] = chart_data["artists"]
    m["arranger"] = chart_data["artists"]
    m["userName"] = chart_data["author"]
    m["playLevel"] = chart_data["rating"]
    m["fillerSec"] = MUS_START_PADDING + waveoffset
    empty = ["description", "collaborationLabel", "videoFileName"]

    for key in empty:
        m[key] = ""
    
    byebye_adios = ["cover", "preview", "bgm", "data", "useSkin",
                    "useBackground", "useEffect", "useParticle", 
                    "author", "artists", "rating", "version", 
                    "source", "name"]
    
    for key in byebye_adios:
        del m[key]
        
    return m