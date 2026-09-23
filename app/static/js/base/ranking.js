let tipoAtual = "Jovem"

let offset = 0
const limit = 5
let carregando = false
let terminou = false

function avatar(nome) {
    return `https://ui-avatars.com/api/?name=${nome}&background=f6a50e&color=fff`
}

async function carregarRanking(reset = false) {

    if (carregando) return

    if (reset) {
        offset = 0
        terminou = false
        document.getElementById("ranking_lista").innerHTML = ""
        document.getElementById("podio").innerHTML = ""
    }

    if (terminou) return

    carregando = true

    const vendedor = document.getElementById("filtroVendedor").value

    const resp = await fetch(`/api/ranking?vendedor=${vendedor}&tipo=${tipoAtual}&limit=${limit}&offset=${offset}`)
    const data = await resp.json()

    const lista = document.getElementById("ranking_lista")
    const podio = document.getElementById("podio")

    if (data.length === 0 && offset === 0) {
        lista.innerHTML = `<p class="text-center text-slate-400">Nenhum vendedor encontrado</p>`
        carregando = false
        return
    }

    if (data.length < limit) {
        terminou = true
    }

    const max = data.length > 0 ? data[0].quantidade : 1

    /* ===== PODIO (sempre recalcula quando reset) ===== */

    if (offset === 0) {

        podio.innerHTML = ""

        data.slice(0, 3).forEach((v, i) => {

            podio.innerHTML += `

<div class="flex flex-col items-center bg-white dark:bg-slate-800 rounded-xl p-4 shadow border">

<img src="${avatar(v.nome)}"
class="w-14 h-14 rounded-full mb-2"/>

<div class="text-lg font-black ${i === 0 ? "text-yellow-500" : ""}">
${i + 1}º
</div>

<p class="font-bold text-center">
${v.nome}
</p>

<p class="text-xs text-slate-400">
${v.quantidade} vendas
</p>

</div>
`
        })
    }

    /* ===== LISTA ===== */

    data.forEach((v, i) => {

        const progresso = v.quantidade > 0
            ? (v.valor_pago / v.valor_total) * 100
            : 0
        const posicao = offset + i + 1

        lista.innerHTML += `

<div class="ranking-card opacity-0 translate-y-3 transition duration-500 flex flex-col gap-3 rounded-xl p-4 bg-white dark:bg-slate-800 border border-primary/10 shadow-sm">

<div class="flex items-center justify-between">

<div class="flex items-center gap-3">

<span class="text-primary font-black text-lg">
${posicao}
</span>

<img src="${avatar(v.nome)}"
class="w-10 h-10 rounded-full"/>

<div>

<p class="font-bold text-secondary dark:text-white">
${v.nome}
</p>

<p class="text-xs text-slate-400">
${v.tipo}
</p>

</div>

</div>

<div class="text-right">

<p class="font-black text-primary">
${v.quantidade}
</p>

<p class="text-xs text-slate-400">
vendas
</p>

</div>

</div>

<div>

<div class="flex justify-between text-xs mb-1">

<span class="text-green-500 font-semibold">
Pagos
</span>

<span class="text-slate-500">
${v.quantidade_paga}/${v.quantidade}
</span>

</div>

<div class="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">

<div
style="width:${progresso}%"
class="h-full bg-primary transition-all duration-700">
</div>

</div>

</div>

<div class="grid grid-cols-3 text-center text-sm">

<div>
<p class="text-slate-400 text-xs">Total</p>
<p class="font-bold text-secondary dark:text-white">
R$ ${v.valor_total.toFixed(2)}
</p>
</div>

<div>
<p class="text-green-500 text-xs">Pago</p>
<p class="font-bold text-green-600">
R$ ${v.valor_pago.toFixed(2)}
</p>
</div>

<div>
<p class="text-red-500 text-xs">Pendente</p>
<p class="font-bold text-red-600">
R$ ${v.valor_pendente.toFixed(2)}
</p>
</div>

</div>

</div>

`
    })

    offset += data.length

    /* animação */

    setTimeout(() => {
        document
            .querySelectorAll(".ranking-card")
            .forEach((card, i) => {
                setTimeout(() => {
                    card.classList.remove("opacity-0", "translate-y-3")
                }, i * 60)
            })
    }, 100)

    carregando = false
}

/* SCROLL INFINITO */

window.addEventListener("scroll", () => {

    if (
        window.innerHeight + window.scrollY
        >= document.body.offsetHeight - 200
    ) {
        carregarRanking()
    }

})

/* FILTRO DE BUSCA */

document
    .getElementById("filtroVendedor")
    .addEventListener("input", () => {
        carregarRanking(true)
    })

/* FILTRO DE TIPO */

document
    .querySelectorAll(".filtroTipo")
    .forEach(btn => {

        btn.addEventListener("click", () => {

            tipoAtual = btn.dataset.tipo

            carregarRanking(true)

        })

    })

carregarRanking(true)