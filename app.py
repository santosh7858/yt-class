import os
import socket
import requests
from flask import Flask, request, jsonify, render_template_string
import yt_dlp
from datetime import datetime
import random

app = Flask(__name__)

# --- CONFIGURATION ---
# Render/HuggingFace systems ke liye standard dynamic configuration bina IPv6 bind error ke
def get_ydl_opts(extra=None):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    }
    if extra:
        opts.update(extra)
    return opts

# --- API ROUTES ---
@app.route('/api/suggestions')
def suggestions():
    query = request.args.get('q', '')
    if not query: return jsonify([])
    try:
        url = f"http://suggestqueries.google.com/complete/search?client=firefox&q={query}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        return jsonify(res.json()[1])
    except:
        return jsonify([])

@app.route('/api/trending')
def trending():
    opts = get_ydl_opts({'extract_flat': True})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            res = ydl.extract_info("https://www.youtube.com/feed/trending", download=False)
            return jsonify(res.get('entries', [])[:30])
    except:
        return jsonify([])

@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    page = int(request.args.get('page', 1))
    current_vid = request.args.get('exclude', '') 
    
    limit = 20
    search_count = page * limit
    opts = get_ydl_opts({'extract_flat': True})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            res = ydl.extract_info(f"ytsearch{search_count}:{query}", download=False)
            entries = res.get('entries', [])
            filtered = [e for e in entries if e.get('id') != current_vid]
            return jsonify(filtered[-(limit):])
    except:
        return jsonify([])

@app.route('/api/stream_info')
def stream_info():
    video_id = request.args.get('v', '')
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = get_ydl_opts({'format': 'best'})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            raw_date = info.get('upload_date', '')
            fmt_date = datetime.strptime(raw_date, "%Y%m%d").strftime("%d %b %Y") if raw_date else "Recent"
            return jsonify({
                'id': info.get('id'),
                'stream_url': info.get('url'),
                'title': info.get('title'),
                'description': info.get('description', '')[:1000],
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'upload_date': fmt_date,
                'duration_string': info.get('duration_string', '0:00'),
                'thumbnail': info.get('thumbnail'),
                'tags': info.get('tags', [])[:5] 
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- UI TEMPLATE ---
LAYOUT = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fluid Pro Ultra | Advanced Player</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdn.fluidplayer.com/v3/current/fluidplayer.min.css" type="text/css"/>
    <script src="https://cdn.fluidplayer.com/v3/current/fluidplayer.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
    <style>
        body { background: #020202; color: #f8fafc; font-family: 'Outfit', sans-serif; scroll-behavior: smooth; }
        .glass { background: rgba(15, 15, 15, 0.85); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.05); }
        .btn-active { background: linear-gradient(135deg, #ef4444, #991b1b) !important; color: white !important; box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }
        .hide-scroll::-webkit-scrollbar { display: none; }
        
        #player-container.mini { position: fixed; bottom: 25px; right: 25px; width: 380px; height: auto; z-index: 1000; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.7); border-radius: 20px; overflow: hidden; border: 1px solid rgba(255,255,255,0.1); }
        #player-container.watch { position: relative; width: 100%; aspect-ratio: 16/9; border-radius: 24px; overflow: hidden; }
        
        .card-hover { transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
        .card-hover:hover { transform: scale(1.03) translateY(-8px); z-index: 10; }
        .video-card-img { aspect-ratio: 16/9; object-fit: cover; border-radius: 14px; }
        
        .loader-dot { animation: pulse 1.5s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        
        .btn-premium { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); transition: all 0.3s; }
        .btn-premium:hover { background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.2); }
        
        #refresh-overlay { position: fixed; inset: 0; background: black; z-index: 10000; display: none; flex-direction: column; items-center; justify-content: center; gap: 20px; transition: opacity 0.5s; }
    </style>
</head>
<body class="pb-24">
    <div id="refresh-overlay">
        <div class="bg-red-600 p-4 rounded-3xl animate-bounce">
            <svg class="w-12 h-12 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
        </div>
        <p class="text-xl font-black tracking-widest animate-pulse uppercase">Refreshing Memory & Playing Next...</p>
    </div>

    <nav class="sticky top-0 z-[100] glass px-8 py-5 flex items-center justify-between border-b border-white/5">
        <div class="flex items-center gap-3 cursor-pointer" onclick="navigate('/')">
            <div class="bg-red-600 p-2.5 rounded-2xl rotate-3">
                <svg class="w-7 h-7 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
            </div>
            <span class="text-3xl font-extrabold tracking-tight uppercase">Fluid <span class="text-red-600">Ultra</span></span>
        </div>

        <div class="relative w-full max-w-xl mx-12">
            <form onsubmit="event.preventDefault(); performSearch();" class="flex items-center group">
                <input id="search-input" type="text" autocomplete="off" placeholder="Artist, Gana ya Album..." class="w-full bg-zinc-900/60 border border-zinc-800 rounded-l-3xl py-4 px-8 focus:outline-none focus:ring-2 focus:ring-red-600/50 transition-all text-lg">
                <button type="submit" class="bg-zinc-800 px-10 py-4 rounded-r-3xl border-l border-zinc-700 hover:bg-red-600 transition-colors">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                </button>
            </form>
            <div id="suggestions-box" class="glass absolute top-full left-0 w-full mt-3 rounded-3xl overflow-hidden shadow-2xl hidden z-[110] border border-white/10"></div>
        </div>

        <div class="hidden lg:flex flex-col items-end gap-1 font-mono">
            <span class="text-[10px] text-green-500 font-bold bg-green-500/10 px-2 py-0.5 rounded">RENDER SERVER ACTIVE</span>
            <span class="text-xs text-zinc-400">Status: Running</span>
        </div>
    </nav>

    <main class="container mx-auto px-6 py-10">
        <div id="main-content"></div>
        <div id="loading-trigger" class="py-16 flex justify-center items-center gap-2 opacity-0">
            <div class="w-3 h-3 bg-red-600 rounded-full loader-dot"></div>
            <div class="w-3 h-3 bg-red-600 rounded-full loader-dot" style="animation-delay: 0.2s"></div>
            <div class="w-3 h-3 bg-red-600 rounded-full loader-dot" style="animation-delay: 0.4s"></div>
        </div>
    </main>

    <div id="player-container" class="hidden">
        <video id="main-video-player"><source id="v-src" src="" type="video/mp4"/></video>
    </div>

    <script>
        let fp = null;
        let curId = null;
        let curData = null;
        let curPage = 1;
        let curQuery = '';
        let isBusy = false;
        
        let relPage = 1;
        let relQuery = '';
        
        let isRepeat = localStorage.getItem('cfg_rep') === 'true';
        let isShuffle = localStorage.getItem('cfg_shf') === 'true';
        let isAutoNext = true;

        const CONTENT = document.getElementById('main-content');
        const PLAYER_BOX = document.getElementById('player-container');
        const INPUT = document.getElementById('search-input');
        const SUGG = document.getElementById('suggestions-box');
        const LOADER = document.getElementById('loading-trigger');
        const REFRESH_OVERLAY = document.getElementById('refresh-overlay');

        window.onpopstate = () => handleRoute();
        function navigate(p) { window.history.pushState({}, '', p); handleRoute(); }
        
        function hardNavigate(p) {
            REFRESH_OVERLAY.style.display = 'flex';
            setTimeout(() => { window.location.href = p; }, 350);
        }

        function handleRoute() {
            const url = new URL(window.location.href);
            const path = url.pathname;
            const vid = url.searchParams.get('v');
            const q = url.searchParams.get('q');

            if(path === '/watch' && vid) {
                renderWatch(vid);
            } else {
                if(curId) {
                    PLAYER_BOX.className = 'mini';
                    document.body.appendChild(PLAYER_BOX);
                }
                if(q) { INPUT.value = q; doSearch(); }
                else loadHome();
            }
        }

        function loadHome() {
            CONTENT.innerHTML = `<div class="flex items-center gap-4 mb-12"><div class="h-px bg-white/10 flex-1"></div><h2 class="text-3xl font-black uppercase tracking-[0.2em] text-red-600">Top Trending</h2><div class="h-px bg-white/10 flex-1"></div></div><div id="v-grid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-8"></div>`;
            fetch('/api/trending').then(r=>r.json()).then(d => renderVideos(d, 'v-grid'));
        }

        function renderVideos(videos, tid, append=false) {
            const g = document.getElementById(tid);
            if(!append) g.innerHTML = '';
            videos.forEach(v => {
                if(!v.id) return;
                const views = formatNum(v.view_count || Math.floor(Math.random()*1000000));
                g.innerHTML += `
                    <div class="card-hover cursor-pointer group" onclick="hardNavigate('/watch?v=${v.id}')">
                        <div class="relative mb-4">
                            <img src="https://img.youtube.com/vi/${v.id}/mqdefault.jpg" class="video-card-img w-full shadow-2xl grayscale-[0.3] group-hover:grayscale-0 transition duration-500">
                            <div class="absolute bottom-3 right-3 bg-red-600 px-3 py-1 rounded-lg text-[10px] font-black shadow-xl">${v.duration_string || '4:20'}</div>
                        </div>
                        <div class="px-1 overflow-hidden">
                            <h3 class="font-bold text-base line-clamp-2 leading-tight group-hover:text-red-500 transition">${v.title}</h3>
                            <p class="text-xs text-zinc-500 font-bold mt-2 uppercase tracking-tighter">${v.uploader || 'YouTube'}</p>
                        </div>
                    </div>
                `;
            });
        }

        function renderWatch(id) {
            CONTENT.innerHTML = `
                <div class="flex flex-col lg:flex-row gap-12">
                    <div class="w-full lg:w-[70%]">
                        <div id="player-anchor" class="bg-black rounded-[2.5rem] overflow-hidden shadow-[0_0_100px_rgba(0,0,0,0.5)] border border-white/5"></div>
                        
                        <div id="v-info" class="mt-10">
                            <div class="flex flex-col gap-6">
                                <h1 id="t-title" class="text-4xl font-black leading-tight tracking-tight">...</h1>
                                
                                <div class="flex flex-wrap items-center justify-between p-7 glass rounded-[2.5rem] border border-white/10 gap-6">
                                    <div class="flex items-center gap-5">
                                        <div class="relative">
                                            <img id="t-avatar" src="" class="w-16 h-16 rounded-[22px] border-2 border-red-600/30 object-cover">
                                            <div class="absolute -bottom-1 -right-1 bg-blue-500 rounded-full p-1 border-2 border-zinc-900">
                                                <svg class="w-2 h-2 text-white" fill="currentColor" viewBox="0 0 20 20"><path d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"></path></svg>
                                            </div>
                                        </div>
                                        <div>
                                            <p id="t-uploader" class="text-xl font-extrabold"></p>
                                            <p id="t-meta" class="text-[10px] text-zinc-500 font-black uppercase tracking-widest mt-1"></p>
                                        </div>
                                    </div>
                                    
                                    <div class="flex items-center gap-3">
                                        <button onclick="toggleRepeat()" id="btn-repeat" class="btn-premium p-4 rounded-3xl flex flex-col items-center gap-1 min-w-[90px]">
                                            <span class="text-xl">🔁</span>
                                            <span class="text-[9px] font-black uppercase">Repeat</span>
                                        </button>
                                        <button onclick="toggleShuffle()" id="btn-shuffle" class="btn-premium p-4 rounded-3xl flex flex-col items-center gap-1 min-w-[90px]">
                                            <span class="text-xl">🔀</span>
                                            <span class="text-[9px] font-black uppercase">Shuffle</span>
                                        </button>
                                    </div>
                                </div>

                                <div class="glass p-8 rounded-[2.5rem] border border-white/5 bg-zinc-900/30">
                                    <p id="t-desc" class="text-zinc-400 text-sm leading-relaxed whitespace-pre-wrap"></p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="w-full lg:w-[30%]">
                        <div class="sticky top-32">
                            <div class="flex items-center justify-between mb-8">
                                <h3 class="text-xl font-black uppercase tracking-widest text-red-600">Fresh Variety</h3>
                                <div class="h-px bg-white/10 flex-1 ml-4"></div>
                            </div>
                            <div id="rel-grid" class="flex flex-col gap-6"></div>
                        </div>
                    </div>
                </div>
            `;

            const anchor = document.getElementById('player-anchor');
            PLAYER_BOX.classList.remove('hidden');
            PLAYER_BOX.className = 'watch';
            anchor.appendChild(PLAYER_BOX);

            curId = id;
            fetch(`/api/stream_info?v=${id}`).then(r=>r.json()).then(d => {
                if(d.error) return;
                curData = d;
                
                document.getElementById('t-title').innerText = d.title;
                document.getElementById('t-uploader').innerText = d.uploader;
                document.getElementById('t-avatar').src = `https://ui-avatars.com/api/?name=${encodeURIComponent(d.uploader)}&background=random&color=fff`;
                document.getElementById('t-meta').innerText = `${formatNum(d.view_count)} Views • ${d.upload_date} • ${d.duration_string}`;
                document.getElementById('t-desc').innerText = d.description;

                if(fp) { fp.destroy(); fp = null; }

                const vTag = document.getElementById('main-video-player');
                vTag.querySelector('source').src = d.stream_url;
                
                fp = fluidPlayer('main-video-player', {
                    layoutControls: {
                        fillToContainer: true,
                        primaryColor: "#ef4444",
                        posterImage: d.thumbnail,
                        autoPlay: true,
                        playbackRateEnabled: true
                    }
                });
                
                vTag.load();
                vTag.play().catch(()=>{});

                vTag.onended = () => {
                    if(isRepeat) {
                        vTag.currentTime = 0;
                        vTag.play();
                    } else if(isAutoNext) {
                        const relatedCards = document.querySelectorAll('.rel-card-link');
                        if(relatedCards.length > 0) {
                            let nextIndex = isShuffle ? Math.floor(Math.random() * relatedCards.length) : 0;
                            const targetId = relatedCards[nextIndex].dataset.vid;
                            hardNavigate(`/watch?v=${targetId}`);
                        }
                    }
                };

                relPage = 1;
                const seedQuery = d.tags.length > 0 ? d.tags.join(' ') : d.uploader;
                relQuery = seedQuery;
                fetchRel(true);
                updateControlsUI();
            });
        }

        function fetchRel(clear=false) {
            if(isBusy) return; isBusy = true;
            if(clear) document.getElementById('rel-grid').innerHTML = '';
            
            fetch(`/api/search?q=${encodeURIComponent(relQuery)}&page=${relPage}&exclude=${curId}`)
                .then(r=>r.json()).then(data => {
                    const g = document.getElementById('rel-grid');
                    data.forEach(v => {
                        if(v.id === curId) return;
                        g.innerHTML += `
                            <div class="rel-card-link flex gap-4 cursor-pointer group p-3 rounded-[20px] hover:bg-white/5 transition" data-vid="${v.id}" onclick="hardNavigate('/watch?v=${v.id}')">
                                <div class="relative w-36 h-20 flex-shrink-0">
                                    <img src="https://img.youtube.com/vi/${v.id}/mqdefault.jpg" class="w-full h-full object-cover rounded-2xl shadow-lg group-hover:scale-105 transition">
                                </div>
                                <div class="flex flex-col justify-center overflow-hidden">
                                    <h4 class="text-xs font-bold line-clamp-2 leading-tight group-hover:text-red-500 transition">${v.title}</h4>
                                    <p class="text-[10px] text-zinc-600 font-black uppercase mt-1 truncate">${v.uploader || ''}</p>
                                </div>
                            </div>
                        `;
                    });
                    relPage++; isBusy = false;
                }).catch(()=>isBusy=false);
        }

        function toggleRepeat() { isRepeat = !isRepeat; localStorage.setItem('cfg_rep', isRepeat); updateControlsUI(); }
        function toggleShuffle() { isShuffle = !isShuffle; localStorage.setItem('cfg_shf', isShuffle); updateControlsUI(); }

        function updateControlsUI() {
            if(!document.getElementById('btn-repeat')) return;
            document.getElementById('btn-repeat').className = isRepeat ? 'btn-premium p-4 rounded-3xl flex flex-col items-center gap-1 min-w-[90px] btn-active' : 'btn-premium p-4 rounded-3xl flex flex-col items-center gap-1 min-w-[90px]';
            document.getElementById('btn-shuffle').className = isShuffle ? 'btn-premium p-4 rounded-3xl flex flex-col items-center gap-1 min-w-[90px] btn-active' : 'btn-premium p-4 rounded-3xl flex flex-col items-center gap-1 min-w-[90px]';
        }

        window.onscroll = () => {
            if(isBusy) return;
            const bottom = (window.innerHeight + window.pageYOffset) >= (document.documentElement.scrollHeight - 1200);
            if(bottom) {
                const path = window.location.pathname;
                if(path === '/search') { fetchResults(); }
                else if(path === '/watch') { fetchRel(); }
            }
        };

        INPUT.oninput = (e) => {
            const q = e.target.value;
            if(q.length < 2) { SUGG.classList.add('hidden'); return; }
            fetch(`/api/suggestions?q=${q}`).then(r=>r.json()).then(d => {
                if(d.length) {
                    SUGG.innerHTML = d.map(s => `<div class="px-8 py-4 hover:bg-zinc-800 cursor-pointer font-bold transition flex items-center gap-3" onclick="clickS('${s}')"><span>🔍</span> ${s}</div>`).join('');
                    SUGG.classList.remove('hidden');
                } else SUGG.classList.add('hidden');
            });
        };
        function clickS(s) { INPUT.value = s; SUGG.classList.add('hidden'); performSearch(); }
        function performSearch() { navigate(`/search?q=${encodeURIComponent(INPUT.value)}`); }

        function doSearch() {
            curQuery = INPUT.value; curPage = 1;
            CONTENT.innerHTML = `<h2 class="text-3xl font-black mb-12 uppercase tracking-tight">Results for <span class="text-red-600">"${curQuery}"</span></h2><div id="v-grid" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-8"></div>`;
            fetchResults();
        }

        function formatNum(n) { 
            if(n >= 1e6) return (n/1e6).toFixed(1)+'M'; 
            if(n >= 1e3) return (n/1e3).toFixed(1)+'K'; 
            return n; 
        }

        handleRoute();
    </script>
</body>
</html>
"""

@app.route('/')
@app.route('/search')
@app.route('/watch')
def index():
    return render_template_string(LAYOUT)

if __name__ == '__main__':
    # Render fallback configurations
    app.run(host='0.0.0.0', port=10000, debug=False)
