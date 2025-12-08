import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(layout="wide", page_title="Simulateur Bilan Hydrique V23")

# --- 2. CSS "INVISIBLE" POUR L'IMPRESSION ---
st.markdown("""
<style>
@media print {
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stHeader"] { display: none; }
    .stButton { display: none; }
    div[data-testid="stToolbar"] { display: none; }
    .stTabs [data-baseweb="tab-list"] { display: none; } /* Cache les onglets à l'impression */
    .block-container { padding-top: 1rem; }
}
/* Style pour le rapport compact */
.report-box {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 5px;
    padding: 10px;
    margin-bottom: 10px;
}
.report-label {
    font-size: 0.85rem;
    color: #6c757d;
    text-transform: uppercase;
    font-weight: 600;
}
.report-value {
    font-size: 1.1rem; /* Police réduite ici */
    font-weight: bold;
    color: #212529;
}
.report-unit {
    font-size: 0.9rem;
    color: #495057;
    font-weight: normal;
}
</style>
""", unsafe_allow_html=True)

st.title("💧 Simulateur Bilan Hydrique V23")
st.caption("Version 23 : Pages séparées & Rapport Compact")

# --- 3. INITIALISATION MÉMOIRE ---
if 'mc_done' not in st.session_state: st.session_state['mc_done'] = False
if 'mc_results' not in st.session_state: st.session_state['mc_results'] = {}
if 'main_results' not in st.session_state: st.session_state['main_results'] = None

# --- 4. BARRE LATÉRALE (PARAMÈTRES) ---
with st.sidebar:
    st.header("1. Paramètres du Projet")
    nom_projet = st.text_input("Nom du Projet", "Mine Site Nord")
    
    st.subheader("Données Physiques")
    vol_min = st.number_input("Volume min. hiver (m³)", value=91712)
    seuil_debordement = st.number_input("Seuil Débordement (m³)", value=330000)
    capacite_traitement = st.number_input("Capacité Pompe (m³/jour)", value=5000)
    
    st.subheader("Bassin Versant")
    surface_bv = st.number_input("Surface Bassin (m²)", value=1700000)
    surface_plan_eau = st.number_input("Surface Plan d'Eau (m²)", value=20000)
    coeff_ruissellement = st.slider("Coeff. Ruissellement", 0.0, 1.0, 0.85)
    
    st.subheader("Neige & Fonte")
    melt_rate = st.number_input("Coeff. Fonte (mm/°C/jour)", value=4.0)
    
    st.markdown("---")
    autres_apports = st.number_input("Autre apport (m³/j)", value=0)
    autres_pertes = st.number_input("Autres pertes (m³/j)", value=452)
    
    st.subheader("Période Traitement")
    mois_options = {"Jan": 1, "Fév": 2, "Mar": 3, "Avr": 4, "Mai": 5, "Juin": 6, "Juil": 7, "Août": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Déc": 12}
    c1, c2 = st.columns(2)
    debut_trait_nom = c1.selectbox("Début", list(mois_options.keys()), index=3)
    fin_trait_nom = c2.selectbox("Fin", list(mois_options.keys()), index=10)
    debut_trait = mois_options[debut_trait_nom]
    fin_trait = mois_options[fin_trait_nom]

    st.header("2. Météo")
    majoration_pluie = st.slider("Ajustement Pluie (%)", -50, 50, 0)
    
    default_data = {
        "Mois": ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"],
        "Pluie (mm)": [43.0, 30.2, 41.0, 46.7, 67.5, 86.4, 105.1, 85.8, 94.4, 75.0, 60.7, 46.2],
        "Evap (mm/j)": [0.0, 0.0, 0.0, 1.0, 3.0, 4.5, 4.5, 3.5, 2.0, 1.0, 0.0, 0.0],
        "Temp (°C)": [-10.0, -8.0, -2.0, 5.0, 12.0, 17.0, 20.0, 19.0, 14.0, 7.0, 0.5, -6.0]
    }
    with st.expander("📝 Éditer Données Mensuelles", expanded=False):
        edited_meteo = st.data_editor(pd.DataFrame(default_data), hide_index=True)

    facteur_pluie = 1 + (majoration_pluie / 100)
    MOYENNES_PLUIE = edited_meteo["Pluie (mm)"].values * facteur_pluie
    MOYENNES_EVAP = edited_meteo["Evap (mm/j)"].values
    MOYENNES_TEMP = edited_meteo["Temp (°C)"].values

# --- 5. MOTEUR DE CALCUL ---
def run_simulation(years=60):
    start_date = pd.to_datetime("2024-01-01")
    dates = pd.date_range(start=start_date, periods=years*365, freq="D")
    n_days = len(dates)
    months_idx = dates.month - 1
    
    daily_avg_rain = np.array([MOYENNES_PLUIE[m] / 30.0 for m in months_idx])
    precip_brute_mm = np.random.exponential(scale=daily_avg_rain, size=n_days)
    temp_base = np.array([MOYENNES_TEMP[m] for m in months_idx])
    temp_simulee = temp_base + np.random.normal(0, 3, n_days)
    evap_simulee_mm = np.array([MOYENNES_EVAP[m] for m in months_idx])
    
    vol_eau = np.zeros(n_days)
    vol_traite = np.zeros(n_days)
    stock_neige = np.zeros(n_days)
    
    current_vol = vol_min 
    current_snowpack = 0.0
    overflow_count = 0
    
    for i in range(n_days):
        m = months_idx[i] + 1
        t = temp_simulee[i]
        p = precip_brute_mm[i]
        
        eau_liquide = 0.0
        if t <= 0:
            current_snowpack += p
        else:
            eau_liquide += p
            fonte = min(current_snowpack, t * melt_rate)
            current_snowpack -= fonte
            eau_liquide += fonte
        stock_neige[i] = current_snowpack

        apport = (eau_liquide/1000)*surface_bv*coeff_ruissellement + (eau_liquide/1000)*surface_plan_eau + autres_apports
        perte = (evap_simulee_mm[i]/1000)*surface_plan_eau + autres_pertes
        current_vol += (apport - perte)
        
        traitement = 0
        if debut_trait <= m <= fin_trait:
            surplus = max(0, current_vol - vol_min)
            traitement = min(capacite_traitement, surplus)
        
        current_vol -= traitement
        if current_vol < 0: current_vol = 0
        if current_vol > seuil_debordement: overflow_count += 1
            
        vol_eau[i] = current_vol
        vol_traite[i] = traitement
        
    return pd.DataFrame({"Date": dates, "Volume": vol_eau, "Traitement": vol_traite, "Neige": stock_neige}), overflow_count

# --- 6. INTERFACE ---
tab_bilan, tab_idf = st.tabs(["🌊 Bilan Hydrique", "⛈️ Gestion des Crues (IDF)"])

with tab_bilan:
    # SOUS-ONGLETS POUR SÉPARER LES ÉCRANS
    subtab_sim, subtab_stress, subtab_report = st.tabs(["1. Simulation (60 ans)", "2. Stress Test", "3. Rapport Final"])
    
    # --- A. SIMULATION PRINCIPALE ---
    with subtab_sim:
        st.markdown("#### 🚀 Simulation Historique")
        if st.button("Lancer Simulation", type="primary"):
            with st.spinner('Calcul en cours...'):
                df_res, jours_debord = run_simulation(years=60)
                st.session_state['main_results'] = {
                    "vol_max": df_res["Volume"].max(),
                    "vol_moy": df_res["Traitement"].sum() / 60,
                    "jours_debord": jours_debord,
                    "df": df_res
                }
        
        res = st.session_state['main_results']
        if res:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=res['df']["Date"], y=res['df']["Volume"], name="Volume (m³)", line=dict(color='#3498db')), secondary_y=False)
            fig.add_trace(go.Scatter(x=res['df']["Date"], y=res['df']["Neige"], name="Neige (mm)", line=dict(color='#bdc3c7'), fill='tozeroy', opacity=0.5), secondary_y=True)
            fig.add_hline(y=seuil_debordement, line_color="red", line_dash="dash", secondary_y=False)
            fig.update_layout(height=500, title="Historique Simulation (60 ans)", margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
            
            # Petits KPI rapides en dessous
            c1, c2, c3 = st.columns(3)
            c1.info(f"Vol Max: {res['vol_max']:,.0f} m³")
            c2.info(f"Moyenne: {res['vol_moy']:,.0f} m³/an")
            if res['jours_debord'] > 0:
                c3.error(f"Débordements: {res['jours_debord']} jours")
            else:
                c3.success("Débordements: 0 jours")

    # --- B. STRESS TEST ---
    with subtab_stress:
        st.markdown("#### 🎲 Analyse de Risque (Monte Carlo)")
        st.caption("Lance 50 simulations parallèles pour définir l'enveloppe de risque à 95%.")
        
        if st.button("Lancer Stress Test", type="primary"):
            progress_bar = st.progress(0)
            sims_vols = []
            cpt_fail = 0
            N_SIMS = 50
            for n in range(N_SIMS):
                df_mc, db_mc = run_simulation(years=10)
                sims_vols.append(df_mc["Volume"].values)
                if db_mc > 0: cpt_fail += 1
                progress_bar.progress((n+1)/N_SIMS)
            
            matrix = np.array(sims_vols)
            max_curve = np.percentile(matrix, 95, axis=0)
            avg_curve = np.mean(matrix, axis=0)
            dates_mc = pd.date_range("2024-01-01", periods=len(avg_curve), freq="D")
            
            st.session_state['mc_results'] = {
                "max_vol_95": np.max(max_curve),
                "prob_fail": (cpt_fail / N_SIMS) * 100,
                "dates": dates_mc, "max_curve": max_curve, "avg_curve": avg_curve
            }
            st.session_state['mc_done'] = True
            progress_bar.empty()

        if st.session_state['mc_done']:
            mc = st.session_state['mc_results']
            fig_mc = go.Figure()
            fig_mc.add_trace(go.Scatter(x=mc['dates'], y=mc['max_curve'], name='Risque 95%', line=dict(color='red', width=1)))
            fig_mc.add_trace(go.Scatter(x=mc['dates'], y=mc['avg_curve'], name='Moyenne', line=dict(color='blue', width=2)))
            fig_mc.add_hline(y=seuil_debordement, line_color="red", line_dash="dash")
            fig_mc.update_layout(height=500, title="Stress Test (Enveloppe de Risque)", margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_mc, use_container_width=True)
            
            col_risk1, col_risk2 = st.columns(2)
            col_risk1.error(f"Pire Cas (95%): {mc['max_vol_95']:,.0f} m³")
            col_risk2.warning(f"Probabilité Échec: {mc['prob_fail']:.1f}%")

    # --- C. RAPPORT FINAL (COMPACT) ---
    with subtab_report:
        res = st.session_state['main_results']
        
        if res:
            with st.container(border=True):
                # En-tête
                c_logo, c_info = st.columns([3, 1])
                with c_logo:
                    st.markdown(f"### 📄 RAPPORT : {nom_projet}")
                with c_info:
                    st.caption(f"Date : {datetime.date.today().strftime('%d/%m/%Y')}")
                
                st.divider()

                # --- 1. HYPOTHÈSES (GRILLE COMPACTE) ---
                st.markdown("**1. HYPOTHÈSES**")
                
                # J'utilise du HTML pur ici pour contrôler la taille de la police (14px au lieu de gros H1)
                html_params = f"""
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 20px;">
                    <div class="report-box"><div class="report-label">Surface Bassin</div><div class="report-value">{surface_bv:,.0f} <span class="report-unit">m²</span></div></div>
                    <div class="report-box"><div class="report-label">Vol. Min Hiver</div><div class="report-value">{vol_min:,.0f} <span class="report-unit">m³</span></div></div>
                    <div class="report-box"><div class="report-label">Capacité Pompe</div><div class="report-value">{capacite_traitement:,.0f} <span class="report-unit">m³/j</span></div></div>
                    <div class="report-box"><div class="report-label">Seuil Max</div><div class="report-value">{seuil_debordement:,.0f} <span class="report-unit">m³</span></div></div>
                    <div class="report-box"><div class="report-label">Fonte Neige</div><div class="report-value">{melt_rate} <span class="report-unit">mm/°C</span></div></div>
                    <div class="report-box"><div class="report-label">Période</div><div class="report-value">{debut_trait_nom} - {fin_trait_nom}</div></div>
                </div>
                """
                st.markdown(html_params, unsafe_allow_html=True)

                st.divider()

                # --- 2. RÉSULTATS (GRILLE COMPACTE) ---
                st.markdown("**2. RÉSULTATS SIMULATION**")
                
                color_db = "#dc3545" if res['jours_debord'] > 0 else "#198754" # Rouge ou Vert
                
                html_res = f"""
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;">
                    <div class="report-box">
                        <div class="report-label">Volume Max Atteint</div>
                        <div class="report-value">{res['vol_max']:,.0f} <span class="report-unit">m³</span></div>
                    </div>
                    <div class="report-box">
                        <div class="report-label">Moyenne Traitée</div>
                        <div class="report-value">{res['vol_moy']:,.0f} <span class="report-unit">m³/an</span></div>
                    </div>
                    <div class="report-box" style="border-left: 5px solid {color_db}">
                        <div class="report-label">Jours Débordement</div>
                        <div class="report-value" style="color: {color_db}">{res['jours_debord']} <span class="report-unit">jours</span></div>
                    </div>
                </div>
                """
                st.markdown(html_res, unsafe_allow_html=True)

                # --- 3. STRESS TEST (SI DISPO) ---
                if st.session_state['mc_done']:
                    st.divider()
                    st.markdown("**3. STRESS TEST (RISQUE)**")
                    mc = st.session_state['mc_results']
                    color_risk = "#dc3545" if mc['prob_fail'] > 0 else "#198754"
                    
                    html_mc = f"""
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;">
                        <div class="report-box">
                            <div class="report-label">Volume Pire Cas (95%)</div>
                            <div class="report-value">{mc['max_vol_95']:,.0f} <span class="report-unit">m³</span></div>
                        </div>
                        <div class="report-box" style="border-left: 5px solid {color_risk}">
                            <div class="report-label">Probabilité Échec</div>
                            <div class="report-value" style="color: {color_risk}">{mc['prob_fail']:.1f} <span class="report-unit">%</span></div>
                        </div>
                    </div>
                    """
                    st.markdown(html_mc, unsafe_allow_html=True)

                # CONCLUSION
                st.divider()
                is_safe = res['jours_debord'] == 0
                if st.session_state['mc_done'] and st.session_state['mc_results']['prob_fail'] > 0:
                    is_safe = False
                
                if is_safe:
                    st.success("✅ **CONCLUSION : CONFORME.** Le système est stable.")
                else:
                    st.error("⚠️ **CONCLUSION : NON-CONFORME.** Des risques de débordement ont été détectés.")

            st.info("🖨️ Allez dans l'onglet **'Rapport Final'** et faites **CTRL + P** pour imprimer.")
        else:
            st.warning("Veuillez lancer la simulation dans l'onglet 1 pour voir le rapport.")

with tab_idf:
    st.header("⛈️ Calculs Hydrauliques (IDF)")
    
    data_idf = {"2 ans": [104,76,54,42,35,22,2.5], "5 ans": [140,105,75,58,48,30,3.5], "10 ans": [165,124,88,68,56,36,4.2], "25 ans": [195,150,110,85,70,45,5.0], "100 ans": [235,180,130,100,85,55,6.5]}
    df_idf = pd.DataFrame(data_idf, index=[5, 10, 15, 30, 60, 120, 1440])
    
    with st.expander("Voir / Modifier Table IDF", expanded=True):
        edited_idf = st.data_editor(df_idf, use_container_width=True)

    c1, c2 = st.columns(2)
    choix_T = c1.selectbox("Période Retour", edited_idf.columns, index=2)
    choix_D = c2.selectbox("Durée Pointe (min)", [d for d in edited_idf.index if d!=1440], index=2)
    
    try:
        i_pointe = edited_idf.loc[choix_D, choix_T]
        i_24h = edited_idf.loc[1440, choix_T] if 1440 in edited_idf.index else 0
        st.info(f"Pointe ({choix_D}min): **{i_pointe} mm/h** | Volume (24h): **{i_24h} mm/h**")
    except: i_pointe, i_24h = 0,0

    st.subheader("Surfaces Drainées")
    df_bassins = pd.DataFrame([{"Desc": "Toiture", "Ha": 1.5, "C": 0.95}, {"Desc": "Parking", "Ha": 0.8, "C": 0.90}, {"Desc": "Pelouse", "Ha": 2.5, "C": 0.25}])
    edited_bassins = st.data_editor(df_bassins, num_rows="dynamic", use_container_width=True)

    if i_pointe > 0 and not edited_bassins.empty:
        res = edited_bassins.copy()
        res["Q_Pointe_m3s"] = (res["Ha"] * res["C"] * i_pointe) / 360
        res["Vol_24h_m3"] = res["Ha"] * res["C"] * i_24h * 240
        
        st.dataframe(res.style.format({"Ha": "{:.2f}", "C": "{:.2f}", "Q_Pointe_m3s": "{:.3f}", "Vol_24h_m3": "{:.0f}"}), use_container_width=True)
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Surface Totale", f"{res['Ha'].sum():.2f} ha")
        k2.metric("Débit Pointe Total", f"{res['Q_Pointe_m3s'].sum():.3f} m³/s")
        k3.metric("Volume 24h", f"{res['Vol_24h_m3'].sum():.0f} m³", delta_color="inverse")