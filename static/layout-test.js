document.querySelectorAll("button[data-width]").forEach(button => button.addEventListener("click", () => { document.getElementById("preview").width = button.dataset.width; document.getElementById("dimensions").textContent = `${button.dataset.width} × 2200 CSS pixels`; }));
document.getElementById("measure").addEventListener("click", () => {
  const d = document.getElementById("preview").contentDocument;
  const w = d.documentElement.clientWidth;
  const controls = [...d.querySelectorAll("main button")].map(e => ({name:e.textContent.trim(), height:Math.round(e.getBoundingClientRect().height)}));
  const overflow = [...d.querySelectorAll("main button,main h1,main h2,.request,.panel")].filter(e => {const r=e.getBoundingClientRect(); return r.right>w+1 || r.left < -1;}).map(e=>e.textContent.slice(0,60));
  document.getElementById("report").textContent=JSON.stringify({viewport:w,documentWidth:d.documentElement.scrollWidth,overflow,controls},null,2);
});
