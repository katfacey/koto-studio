"""Exercise real editor panel resizing in Chromium against an isolated backend."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from koto.runtime import runtime_environment


def main():
    from playwright.sync_api import sync_playwright
    output = ROOT / "runtime" / "validation"
    output.mkdir(parents=True, exist_ok=True)
    url = "http://127.0.0.1:18765"
    with tempfile.TemporaryDirectory(prefix="KOTO browser project ") as tmp:
        env = runtime_environment()
        env.update({"KOTO_DATA_DIR": tmp, "PYTHONPATH": str(ROOT / "backend"), "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / "runtime/cache/playwright")})
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = env["PLAYWRIGHT_BROWSERS_PATH"]
        with (output / "browser-server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "koto.app:app", "--host", "127.0.0.1", "--port", "18765"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError((output / "browser-server.log").read_text(encoding="utf-8"))
                    try:
                        with opener.open(url + "/api/health", timeout=1) as response:
                            if json.load(response).get("local"):
                                break
                    except OSError:
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError("Browser test backend did not start")
                errors = []
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1600, "height": 1000})
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    try:
                        page.goto(url, wait_until="networkidle")
                        page.locator('.app-shell').wait_for()
                        assert page.locator('[data-panel-resize]').count() == 4
                        def dimension(selector, prop):
                            return page.locator(selector).bounding_box()[prop]
                        def drag(kind, dx, dy):
                            box = page.locator(f'[data-panel-resize="{kind}"]').bounding_box()
                            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                            page.mouse.move(x, y)
                            page.mouse.down()
                            page.mouse.move(x + dx, y + dy, steps=8)
                            page.mouse.up()
                        left = dimension('.left-panel', 'width')
                        right = dimension('.right-panel', 'width')
                        timeline = dimension('.timeline-panel', 'height')
                        dialogue = dimension('.dialogue-editor', 'height')
                        drag('left', 60, 0)
                        assert abs(dimension('.left-panel', 'width') - left - 60) < 2
                        drag('right', -40, 0)
                        assert abs(dimension('.right-panel', 'width') - right - 40) < 2
                        drag('timeline', 0, -40)
                        assert abs(dimension('.timeline-panel', 'height') - timeline - 40) < 2
                        drag('dialogue', 0, -25)
                        assert abs(dimension('.dialogue-editor', 'height') - dialogue - 25) < 2
                        page.reload(wait_until='networkidle')
                        page.locator('.app-shell').wait_for()
                        assert abs(dimension('.left-panel', 'width') - left - 60) < 2
                        handle = page.locator('[data-panel-resize="left"]')
                        handle.focus()
                        page.keyboard.press('ArrowRight')
                        assert abs(dimension('.left-panel', 'width') - left - 70) < 2
                        handle.dblclick()
                        assert abs(dimension('.left-panel', 'width') - left) < 2
                        # These operations use real pointer input and the persisted project API.
                        pid = page.evaluate("localStorage.getItem('koto-project')")
                        def project():
                            return page.request.get(f'{url}/api/projects/{pid}').json()
                        def save():
                            page.keyboard.press('Control+s')
                            page.wait_for_function("document.querySelector('#save-status')?.textContent === 'Project saved locally'")
                        initial = project()
                        clip_id = initial['dialogue'][0]['id']
                        first, second = [s['id'] for s in initial['speakers']]
                        clip = page.locator(f'.dialogue-clip[data-id="{clip_id}"]')
                        clip.scroll_into_view_if_needed()
                        a = clip.bounding_box()
                        target = page.locator(f'[data-speaker-lane="{second}"]')
                        target.scroll_into_view_if_needed()
                        b = target.bounding_box()
                        x, y = a['x'] + a['width']/2, a['y'] + a['height']/2
                        page.keyboard.down('Shift')
                        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+20,b['y']+b['height']/2,steps=8);page.mouse.up()
                        page.keyboard.up('Shift')
                        assert page.locator(f'[data-speaker-lane="{second}"] .dialogue-clip[data-id="{clip_id}"]').count()==1
                        save()
                        moved = next(l for l in project()['dialogue'] if l['id']==clip_id)
                        assert moved['speaker']==second and moved['start']==initial['dialogue'][0]['start']
                        # A horizontal drag moves the clip at the source frame rate.
                        clip=page.locator(f'.dialogue-clip[data-id="{clip_id}"]');a=clip.bounding_box()
                        x,y=a['x']+a['width']/2,a['y']+a['height']/2
                        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+30,y,steps=8);page.mouse.up();save()
                        retimed=next(l for l in project()['dialogue'] if l['id']==clip_id)
                        assert retimed['start']>moved['start'] and retimed['source_start']==moved['start']
                        # Move a whole speaker lane by its grip.
                        grip=page.locator(f'[data-reorder-speaker="{second}"]');a=grip.bounding_box()
                        b=page.locator(f'[data-speaker-lane="{first}"]').bounding_box()
                        page.mouse.move(a['x']+a['width']/2,a['y']+a['height']/2);page.mouse.down()
                        page.mouse.move(a['x']+a['width']/2,b['y']+3,steps=8);page.mouse.up();save()
                        assert project()['speakers'][0]['id']==second
                        page.locator(f'.track-control[data-track="speaker"][data-id="{second}"]').click()
                        page.locator('.track-control[data-track="video"]').click()
                        page.locator('.track-control[data-track="subtitles"]').click();save()
                        page.reload(wait_until='networkidle')
                        assert page.locator('.preview-frame.video-hidden').count()==1
                        assert page.locator(f'[data-speaker-lane="{second}"].track-muted').count()==1
                        saved=project();assert saved['settings']['video_visible'] is False
                        assert saved['settings']['subtitles_visible'] is False
                        # Original-reference selection persists, chooses XTTS and retains uploaded samples.
                        page.locator(f'.speaker-card[data-id="{second}"]').click()
                        page.locator('[data-field="speaker.use_source_reference"]').check()
                        assert page.locator('[data-field="speaker.adapter"]').input_value()=='xtts'
                        save();assert next(sp for sp in project()['speakers'] if sp['id']==second)['use_source_reference'] is True
                        page.locator('[data-field="speaker.use_source_reference"]').uncheck();save()
                        assert not next(sp for sp in project()['speakers'] if sp['id']==second)['use_source_reference']
                        # Show the monitor again for the screenshot.
                        page.locator('[data-act="tab"][data-tab="Timeline"]').click()
                        page.locator('.track-control[data-track="video"]').click()
                        page.locator('.track-control[data-track="subtitles"]').click();save()
                        # Stored suggestion data is an explicit UI fixture; no LLM output is simulated.
                        current=project();selected=current['dialogue'][0]
                        selected['alternatives']={'basis':{k:selected.get(k) for k in ('source','subtitle','translation','start','end')},'suggestions':[{'text':'Wait.'},{'text':'Please stay right here.'},{'text':'Please wait here until the next train arrives.'}]}
                        response=page.request.patch(f'{url}/api/projects/{pid}',data={'revision':current['revision'],'dialogue':current['dialogue']})
                        assert response.ok, response.text()
                        page.reload(wait_until='networkidle')
                        assert page.locator('.translation-option').count()==3
                        page.locator('[data-act="use-alternative"][data-index="1"]').click();save()
                        assert project()['dialogue'][0]['translation']=='Please stay right here.'
                        assert page.locator('.translation-option').count()==0
                        assert page.locator('.clip-timing-dot').count()>0
                        # Exercise actual browser audio playback and live mute with a real PCM fixture.
                        from koto.media import binary
                        take=Path(tmp)/'browser-take.wav'
                        subprocess.run([binary('ffmpeg'),'-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=2:sample_rate=48000','-ac','2',str(take)],check=True)
                        response=page.request.post(f'{url}/api/projects/{pid}/dialogue/{clip_id}/audio',multipart={'file':{'name':'browser-take.wav','mimeType':'audio/wav','buffer':take.read_bytes()}})
                        assert response.ok,response.text()
                        page.reload(wait_until='networkidle')
                        page.evaluate("window.kotoAudio=[];const NativeAudio=window.Audio;window.Audio=function(...args){const audio=new NativeAudio(...args);window.kotoAudio.push(audio);return audio;}")
                        # The second speaker was muted above; enable it for the playback check.
                        page.locator(f'.track-control[data-track="speaker"][data-id="{second}"]').click()
                        page.locator(f'.dialogue-clip[data-id="{clip_id}"]').click()
                        page.locator('[data-act="dub"]').click();page.locator('[data-act="play"]').click()
                        page.wait_for_function('window.kotoAudio.some(a=>!a.paused&&a.currentTime>.08)')
                        page.locator(f'.track-control[data-track="speaker"][data-id="{second}"]').click()
                        page.wait_for_function('window.kotoAudio.length>0&&window.kotoAudio.every(a=>a.paused)')
                        page.locator(f'.track-control[data-track="speaker"][data-id="{second}"]').click()
                        page.wait_for_function('window.kotoAudio.some(a=>!a.paused)')
                        page.locator('[data-act="play"]').click()
                        page.wait_for_function('window.kotoAudio.every(a=>a.paused)');save()
                        # A measured long take appears before render and can be fitted without regeneration.
                        original_line=project()['dialogue'][0]
                        page.locator('[data-act="timeline-tab"]').click()
                        page.locator('[data-field="line.end"]').fill(str(original_line['start']+1.7))
                        page.locator('[data-field="line.auto_fit"]').uncheck();save()
                        page.locator('[data-act="export"]').click()
                        issue=page.locator('.export-issue').filter(has=page.locator(f'[data-act="review-timing"][data-id="{clip_id}"]'))
                        assert 'Take 2.0s / 1.7s slot' in issue.inner_text()
                        issue.locator('[data-act="review-timing"]').click()
                        page.locator('[data-act="fix-timing"]').click();save()
                        fitted=project()['dialogue'][0]
                        assert fitted['auto_fit'] and fitted['audio']['asset']==original_line['audio']['asset']
                        assert fitted['source_end']==original_line['source_end']
                        page.locator('[data-act="export"]').click()
                        assert page.locator(f'.export-issue [data-id="{clip_id}"]').count()==0
                        page.get_by_role('button',name='Back to editor',exact=True).click()
                        page.locator('[data-field="line.end"]').fill(str(original_line['end']));save()
                        page.locator(f'.speaker-card[data-id="{second}"]').click()
                        # Autosave uses the real PATCH endpoint, including typing during a delayed response.
                        page.locator('[data-field="line.translation"]').fill('Please wait here.')
                        page.wait_for_function("document.querySelector('#save-status')?.textContent==='Project saved locally'")
                        assert project()['dialogue'][0]['translation']=='Please wait here.'
                        page.evaluate("window.nativeKotoFetch=window.fetch;window.heldSave=false;window.fetch=async function(input,init){const response=await window.nativeKotoFetch(input,init);if(init?.method==='PATCH'){window.heldSave=true;await new Promise(r=>setTimeout(r,1200));window.heldSave=false;}return response;}")
                        page.locator('[data-field="line.translation"]').fill('Wait beside me.')
                        page.wait_for_function('window.heldSave')
                        page.locator('[data-field="line.translation"]').fill('Stay beside me.')
                        page.wait_for_function("document.querySelector('#save-status')?.textContent==='Project saved locally'")
                        assert page.locator('[data-field="line.translation"]').input_value()=='Stay beside me.'
                        assert project()['dialogue'][0]['translation']=='Stay beside me.'
                        # A save response must not detach the line object being trimmed.
                        old_end=project()['dialogue'][0]['end']
                        page.locator('[data-field="line.translation"]').fill('Remain beside me.')
                        page.wait_for_function('window.heldSave')
                        handle=page.locator(f'.dialogue-clip[data-id="{clip_id}"] [data-trim="end"]')
                        box=handle.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']/2
                        page.mouse.move(x,y);page.mouse.down()
                        page.wait_for_function('!window.heldSave')
                        page.mouse.move(x+8,y,steps=4);page.mouse.up()
                        page.wait_for_function("document.querySelector('#save-status')?.textContent==='Project saved locally'")
                        assert project()['dialogue'][0]['end']>old_end
                        page.evaluate('window.fetch=window.nativeKotoFetch')
                        # Real installed Piper generates a line, then batches the remaining lines for this speaker.
                        page.locator('[data-field="speaker.adapter"]').select_option('piper')
                        page.locator('[data-act="original"]').click()
                        page.locator('[data-act="generate-line"]').click()
                        page.locator('[data-act="dub"].active').wait_for(timeout=60000)
                        assert 'English mix selected' in page.locator('.notice-toast').inner_text()
                        first_take=project()['dialogue'][0]['audio']['asset']
                        assert project()['dialogue'][0]['audio']['kind']=='generated'
                        page.locator(f'.speaker-card[data-id="{second}"]').click()
                        page.locator('[data-act="original"]').click()
                        page.locator('[data-act="generate-speaker"]').click()
                        page.locator('[data-act="dub"].active').wait_for(timeout=60000)
                        actual=project()
                        assert all(l['audio'] for l in actual['dialogue'] if l['speaker']==second)
                        assert actual['dialogue'][0]['audio']['asset']==first_take
                        # Keyboard deletion must work after leaving text editing, and Undo must restore it.
                        page.locator('[data-act="tab"][data-tab="Timeline"]').click()
                        count=page.locator('.dialogue-clip').count()
                        page.locator('[data-field="line.translation"]').focus()
                        page.keyboard.press('Delete')
                        assert page.locator('.dialogue-clip').count()==count
                        page.locator(f'.dialogue-clip[data-id="{clip_id}"]').click()
                        assert page.locator(f'.dialogue-clip[data-id="{clip_id}"]').evaluate('(el)=>el===document.activeElement')
                        page.keyboard.press('Delete')
                        assert page.locator('.dialogue-clip').count()==count-1
                        page.wait_for_function("document.querySelector('#save-status')?.textContent==='Project saved locally'")
                        assert len(project()['dialogue'])==count-1
                        page.keyboard.press('Control+z')
                        assert page.locator(f'.dialogue-clip[data-id="{clip_id}"]').count()==1
                        page.locator(f'.dialogue-clip[data-id="{clip_id}"]').click()
                        page.keyboard.press('Backspace')
                        assert page.locator('.dialogue-clip').count()==count-1
                        page.keyboard.press('Control+z');save()
                        # Render an actual overlong take through the warning UI, including its tail past video.
                        source=Path(tmp)/'soft-export-source.mkv'
                        subprocess.run([binary('ffmpeg'),'-v','error','-y','-f','lavfi','-i','color=c=black:s=160x90:r=24:d=2','-c:v','libx264',str(source)],check=True)
                        created=page.request.post(f'{url}/api/projects',data={'name':'Timing warning validation'}).json()
                        warning_pid=created['id']
                        imported=page.request.post(f'{url}/api/projects/{warning_pid}/media',multipart={'file':{'name':source.name,'mimeType':'video/x-matroska','buffer':source.read_bytes()}})
                        assert imported.ok,imported.text()
                        current=imported.json()
                        dialogue=[{'id':'warning-line','speaker':current['speakers'][0]['id'],'start':1.5,'end':1.6,'source':'','subtitle':'','translation':'Explicit PCM timing fixture.','audio':None,'auto_fit':False}]
                        changed=page.request.patch(f'{url}/api/projects/{warning_pid}',data={'revision':current['revision'],'dialogue':dialogue,'settings':{**current['settings'],'background_mode':'silence'}})
                        assert changed.ok,changed.text()
                        attached=page.request.post(f'{url}/api/projects/{warning_pid}/dialogue/warning-line/audio',multipart={'file':{'name':take.name,'mimeType':'audio/wav','buffer':take.read_bytes()}})
                        assert attached.ok,attached.text()
                        page.evaluate('(pid)=>localStorage.setItem("koto-project",pid)',warning_pid)
                        page.reload(wait_until='networkidle')
                        page.locator('[data-act="export"]').click()
                        assert 'Recommended: fix audio timing' in page.locator('.export-timing-warning').inner_text()
                        render=page.get_by_role('button',name='Render anyway',exact=True)
                        assert render.is_enabled()
                        render.click()
                        page.locator('.job-row.job-completed').wait_for(timeout=60000)
                        assert 'timing warnings' in page.locator('.job-row.job-completed').inner_text()
                        assert page.locator('.job-row.job-completed .job-warnings').count()==1
                        completed=page.request.get(f'{url}/api/projects/{warning_pid}/jobs').json()[0]
                        assert completed['status']=='completed' and completed['result']['warnings']
                        assert completed['result']['duration']>=3.5
                        unchanged=page.request.get(f'{url}/api/projects/{warning_pid}').json()['dialogue'][0]
                        assert unchanged['start']==1.5 and unchanged['end']==1.6
                        download=page.locator('.job-row.job-completed a[download]')
                        assert page.request.get(url+download.get_attribute('href')).ok
                        # Return to the labeled sample for the editor screenshot and remaining queue check.
                        current=project()
                        restored=page.request.patch(f'{url}/api/projects/{pid}',data={'revision':current['revision'],'dialogue':actual['dialogue']})
                        assert restored.ok,restored.text()
                        # Text restoration can invalidate the old take; attach it once text matches.
                        restored_takes=page.request.patch(f'{url}/api/projects/{pid}',data={'revision':restored.json()['revision'],'dialogue':actual['dialogue']})
                        assert restored_takes.ok,restored_takes.text()
                        assert restored_takes.json()['dialogue'][0]['audio']['asset']==first_take
                        page.evaluate('(pid)=>localStorage.setItem("koto-project",pid)',pid)
                        page.reload(wait_until='networkidle')
                        page.locator(f'.speaker-card[data-id="{second}"]').click()
                        page.evaluate('document.fonts.ready')
                        page.screenshot(path=str(output / 'koto-editor.png'), full_page=True)
                        # Functional separation controls. Inference is checked separately
                        # with real weights in the dedicated separation-worker CI job.
                        page.locator('[data-kind="separate"]').click()
                        page.locator('.modal-separation').wait_for()
                        assert page.locator('.modal-separation').get_by_text('Saved results',exact=True).count()==1
                        page.locator('[data-field="adapter.separation"]').select_option('audio-separator')
                        page.locator('[data-field="model.separation.model"]').select_option('bs-roformer-viperx')
                        page.locator('.separation-advanced').wait_for(state='attached')
                        assert page.locator('.modal-separation').get_by_text('Window overlap count',exact=True).count()==1
                        page.locator('[data-act="separation-selection"]').click()
                        bounds=project()['dialogue']
                        assert float(page.locator('[data-separation-range="end"]').input_value())>float(page.locator('[data-separation-range="start"]').input_value())
                        assert page.locator('[data-act="separation-preview"]').is_disabled()
                        assert page.locator('[data-act="separation-full"]').is_disabled()
                        assert page.locator('[data-act="download-separation-model"]').is_enabled()
                        page.screenshot(path=str(output / 'koto-separation.png'), full_page=True)
                        page.locator('[data-act="close-modal"]').click()
                        page.locator('[data-act="save"]').click()
                        # Reusable voices and takes use real backend endpoints and actual Piper output.
                        page.locator(f'.speaker-card[data-id="{second}"]').click()
                        page.locator('[data-act="voice-library"]').click()
                        page.locator('.modal-voice-library').wait_for()
                        page.locator('[data-field="library.name"]').fill('Recurring test character')
                        page.locator('[data-act="save-library-voice"]').click()
                        page.locator('.voice-library-row').filter(has_text='Recurring test character').wait_for(timeout=60000)
                        profile=page.request.get(url+'/api/voices').json()[0]
                        page.locator(f'[data-act="assign-library-voice"][data-id="{profile["id"]}"]').click()
                        page.locator('[data-act="close-modal"]').click()
                        assert project()['speakers'][1]['voice_profile']['version']==1
                        page.locator('[data-act="timeline-tab"]').click()
                        page.locator('[data-field="clip.reference_text"]').fill('Clip-only override')
                        save()
                        assert project()['dialogue'][0]['voice']['reference_text']=='Clip-only override'
                        assert not project()['dialogue'][1].get('voice',{}).get('reference_text')
                        history=project()['takes'][clip_id]
                        assert len(history)>=1
                        page.locator('[data-field="selected-take"]').select_option(history[0]['id'])
                        page.wait_for_function("document.querySelector('.take-status')?.textContent.includes('Voice ready')")
                        assert project()['dialogue'][0]['audio']['asset']==history[0]['audio']['asset']
                        page.locator(f'.speaker-card[data-id="{second}"]').click()
                        page.locator('[data-act="voice-library"]').click()
                        page.locator('[data-act="revise-library-voice"]').click()
                        page.locator('.voice-library-row').filter(has_text='Recurring test character').filter(has_text='Version 2').wait_for(timeout=60000)
                        assert project()['speakers'][1]['voice_profile']['version']==1
                        page.screenshot(path=str(output/'koto-voice-library.png'),full_page=True)
                        page.locator('[data-act="close-modal"]').click()
                        # The queue data below is an explicit UI fixture; no inference is simulated.
                        fixture = [{"id": "ui-fixture", "kind": "prepare", "status": "running", "progress": .5, "message": "UI fixture progress", "result": {}}]
                        page.route('**/api/projects/*/jobs', lambda route: route.fulfill(json=fixture))
                        page.reload(wait_until='networkidle')
                        page.locator('.queue-summary [data-act="cancel"]').wait_for()
                        cancel = page.locator('.queue-summary [data-act="cancel"] svg path')
                        assert cancel.get_attribute('d') == 'm6 6 12 12M6 18 18 6'
                        assert not errors, errors
                    except Exception:
                        page.screenshot(path=str(output / 'koto-editor.png'), full_page=True)
                        print('Browser diagnostic:', page.evaluate("({url:location.href,tracks:Array.from(document.querySelectorAll('[data-track]')).map(n=>({class:n.className,track:n.dataset.track,id:n.dataset.id})),errors:document.querySelector('.error-toast')?.textContent})"))
                        raise
                    browser.close()
                print('Real Chromium checks passed: panel resizing, clip reassignment and retiming, lane ordering, mutes, visibility, original-reference selection, export timing warnings/render-anyway with full tail audio, preflight/fix, timing hints and suggestion selection, real live audio/mutes, autosave typing/trim races, real Piper generation/batching, English-mix completion, keyboard delete/undo, persistence, and Cancel X.')
            finally:
                if server.poll() is None:
                    server.terminate()
                    try:
                        server.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)


if __name__ == "__main__":
    main()
