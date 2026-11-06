/* Fun Facts standalone browser features. No ASP.NET or server API required. */
(() => {
  "use strict";
  const DATA = "/facts.json";
  let loaded;
  const load = () => loaded ||= fetch(DATA).then(r => {if (!r.ok) throw Error("Facts index unavailable"); return r.json();});
  const safe = s => String(s || "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const store = (key, otherwise=[]) => {try {return JSON.parse(localStorage.getItem(key)) || otherwise;} catch(e){return otherwise;}};
  const put = (key, value) => {try {localStorage.setItem(key, JSON.stringify(value));} catch(e){}};
  const cards = items => items.map(x => '<a class="ff-card cat-'+safe(x.category)+'" href="/'+encodeURIComponent(x.slug)+'"><span class="ff-card__media"><img loading="lazy" width="800" height="450" src="'+safe(x.image)+'" alt="'+safe(x.title)+'"></span><span class="ff-card__title">'+safe(x.title)+'</span></a>').join("");

  const p = new URLSearchParams(location.search);
  const n = Number(p.get("page"));
  const cat = location.pathname.match(/^\/(animals|space|places|science-nature|culture-life|people-history|fun-facts-for-kids)\/?$/);
  if (cat && Number.isInteger(n) && n > 1) {
    location.replace('/'+cat[1]+'/page/'+n+'/'+location.hash);
    return;
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.getRegistrations().then(arr=>arr.forEach(reg=>reg.unregister())).catch(()=>{});
  }

  const header = document.querySelector(".ff-header");
  const menu = document.getElementById("ffMenu");
  const searchBox = document.getElementById("globalSearch");
  document.addEventListener("click", e => {
    const toggle = e.target.closest("[data-ff-toggle]");
    if (!toggle) return;
    const name = toggle.getAttribute("data-ff-toggle");
    const open = toggle.getAttribute("aria-expanded") !== "true";
    document.querySelectorAll("[data-ff-toggle]").forEach(x=>x.setAttribute("aria-expanded","false"));
    if (header) header.classList.remove("is-search-open");
    if (menu) menu.hidden = true;
    if (!open) return;
    toggle.setAttribute("aria-expanded","true");
    if (name === "search") {if(header) header.classList.add("is-search-open"); searchBox?.focus();}
    else if (menu) menu.hidden = false;
  });
  document.addEventListener("keydown", e => {
    if(e.key !== "Escape") return;
    if(header) header.classList.remove("is-search-open");
    if(menu) menu.hidden=true;
    document.querySelectorAll("[data-ff-toggle]").forEach(x=>x.setAttribute("aria-expanded","false"));
  });

  const suggestion = document.getElementById("searchSuggest");
  if (searchBox && suggestion) {
    let timer;
    searchBox.addEventListener("input",() => {
      clearTimeout(timer);
      const q=searchBox.value.trim().toLowerCase();
      if(q.length < 2) {suggestion.replaceChildren(); return;}
      timer=setTimeout(async() => {
        try {
          const items=(await load()).filter(x=>x.title.toLowerCase().includes(q)).slice(0,8);
          suggestion.innerHTML=items.length ? '<ul class="ff-suggest" role="listbox">'+items.map(x=>'<li class="ff-suggest__option" role="option"><a href="/'+encodeURIComponent(x.slug)+'">'+safe(x.title)+'</a></li>').join('')+'</ul>':'';
        } catch(err) {suggestion.replaceChildren();}
      },180);
    });
  }
  document.querySelectorAll("form").forEach(form=>{
    if((form.getAttribute("action")||"").startsWith("/search")){
      form.addEventListener("submit",e=>{e.preventDefault();const input=form.querySelector('input[name="q"]')||searchBox;location.href="/search?q="+encodeURIComponent(input?.value||"");});
    }
  });
  const results=document.getElementById("ff-static-search-results");
  if(results) (async()=>{
    const q=(new URLSearchParams(location.search).get("q")||"").trim();
    if(!q) {results.innerHTML='<p>Enter a keyword to search Fun Facts.</p>';return;}
    try {
      const found=(await load()).filter(x=>x.title.toLowerCase().includes(q.toLowerCase()));
      results.innerHTML='<h2 class="ff-section__title">'+found.length+' results for "'+safe(q)+'"</h2><div class="ff-grid">'+cards(found.slice(0,240))+'</div>';
    } catch(err) {results.textContent="Search index is temporarily unavailable.";}
  })();

  const saved=store("funfactsx_saved",[]);
  const idOf=el=>Number(el.closest("[data-ff-id]")?.getAttribute("data-ff-id")||el.getAttribute("data-ff-save")||0);
  const refreshSaved=()=>document.querySelectorAll("[data-ff-save]").forEach(el=>{
    const yes=saved.includes(idOf(el));
    el.setAttribute("aria-pressed",yes?"true":"false");
    const label=el.querySelector("span");
    if(label && /^(save|saved)$/i.test(label.textContent.trim()))label.textContent=yes?"Saved":"Save";
  });
  refreshSaved();
  document.addEventListener("click",e=>{
    const btn=e.target.closest("[data-ff-save]");
    if(!btn) return;
    e.preventDefault();
    const id=idOf(btn);if(!id)return;
    const index=saved.indexOf(id);
    if(index<0)saved.push(id);else saved.splice(index,1);
    put("funfactsx_saved",saved);
    refreshSaved();
  });
  const activeFact=document.querySelector("[data-ff-fact][data-ff-id]");
  if(activeFact){
    const history=store("funfactsx_history",[]);
    const id=Number(activeFact.getAttribute("data-ff-id")||0);
    if(id){put("funfactsx_history",[{i:id,t:Date.now()},...history.filter(x=>x.i!==id)].slice(0,2000));}
  }
  document.addEventListener("click",async e=>{
    const next=e.target.closest("[data-ff-next],[data-ff-shuffle]");
    if(!next)return;
    e.preventDefault();
    try {
      let arr=await load();
      const scope=next.closest("[data-ff-scope]")?.getAttribute("data-ff-scope");
      const here=location.pathname.replace(/^\//,"").replace(/\.html$/,"");
      if(scope && scope!=="all" && scope!=="kids")arr=arr.filter(x=>x.category===scope);
      arr=arr.filter(x=>x.slug!==here);
      if(arr.length)location.href="/"+pick(arr).slug;
    } catch(err){location.href="/random-fun-facts";}
  });
  document.addEventListener("click",e=>{
    const share=e.target.closest("[data-ff-share]");
    if(!share)return;
    e.preventDefault();
    const s=share.closest("[data-ff-slug]")?.getAttribute("data-ff-slug");
    const url=s?location.origin+"/"+s:location.href;
    if(navigator.share)navigator.share({title:document.title,url}).catch(()=>{});
    else if(navigator.clipboard)navigator.clipboard.writeText(url).catch(()=>prompt("Copy URL:",url));
    else prompt("Copy URL:",url);
  });
  document.addEventListener("click", async e=>{
    const more=e.target.closest(".ff-popular__more");
    if(!more)return;
    e.preventDefault();
    const grid=more.closest(".ff-popular")?.querySelector(".ff-grid");
    if(!grid)return;
    try{
      const existing=new Set(Array.from(grid.querySelectorAll("a.ff-card")).map(x=>(x.getAttribute("href")||"").split("/").pop()));
      const fresh=(await load()).filter(x=>!existing.has(x.slug)).sort(()=>Math.random()-.5).slice(0,4);
      grid.insertAdjacentHTML("beforeend",cards(fresh));
      if(!fresh.length)more.hidden=true;
    }catch(err){more.hidden=true;}
  });
  document.addEventListener("click",e=>{
    const reshuffle=e.target.closest("[data-ff-reshuffle]");
    if(!reshuffle)return;
    const grid=reshuffle.closest(".ff-popular")?.querySelector(".ff-grid");
    if(grid)Array.from(grid.children).sort(()=>Math.random()-.5).forEach(x=>grid.appendChild(x));
  });
  document.querySelectorAll("img[data-src]").forEach(img=>{
    if(img.getAttribute("data-src"))img.src=img.getAttribute("data-src");
    if(img.getAttribute("data-srcset"))img.srcset=img.getAttribute("data-srcset");
  });
})();
