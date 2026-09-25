document.addEventListener("DOMContentLoaded", () => {
    const list = document.getElementById("lista-despesas");
    const filters = document.getElementById("filtros-despesas");
    const error = document.getElementById("despesas-erro");
    const money = value => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    const load = async () => {
        try {
            const response = await fetch(`/despesas?${new URLSearchParams(new FormData(filters))}`, { headers: { Accept: "application/json" } });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Não foi possível carregar as despesas.");
            error.classList.add("hidden");
            list.innerHTML = data.length ? data.map(item => `<article class="rounded-xl border border-primary/10 bg-white p-5 shadow-sm"><div class="flex items-start justify-between gap-3"><div><p class="text-sm text-slate-500">${new Date(item.data_compra).toLocaleDateString("pt-BR")}</p><h2 class="font-bold text-secondary">${item.fornecedor || "Sem fornecedor"}</h2></div><span class="rounded-full px-3 py-1 text-xs font-bold ${item.status === "pago" ? "bg-green-100 text-green-700" : item.status === "cancelado" ? "bg-slate-200 text-slate-600" : "bg-amber-100 text-amber-700"}">${item.status}</span></div><p class="mt-3 text-sm text-slate-500">${item.categoria} · ${item.items.length} material(is)</p><p class="mt-1 text-xl font-extrabold text-primary">${money(item.valor_total)}</p><div class="mt-4 flex gap-2">${item.status !== "cancelado" ? `<a href="/despesas/${item.id}/editar" class="rounded-lg border border-slate-200 px-3 py-2 text-sm font-bold">Editar</a><button data-cancel="${item.id}" class="rounded-lg border border-red-200 px-3 py-2 text-sm font-bold text-red-700">Cancelar</button>` : ""}</div></article>`).join("") : `<div class="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-slate-500 md:col-span-2 lg:col-span-3">Nenhuma despesa encontrada.</div>`;
        } catch (exception) { error.textContent = exception.message; error.classList.remove("hidden"); }
    };
    filters.addEventListener("change", load); filters.addEventListener("input", load);
    list.addEventListener("click", async event => { const button = event.target.closest("[data-cancel]"); if (!button || !window.confirm("Cancelar esta despesa?")) return; const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content; const response = await fetch(`/despesas/${button.dataset.cancel}/cancelar`, { method: "POST", headers: { Accept: "application/json", "X-CSRFToken": csrfToken } }); if (!response.ok) { const data = await response.json().catch(() => ({})); error.textContent = data.error || "Não foi possível cancelar a despesa."; error.classList.remove("hidden"); return; } load(); });
    load();
});
