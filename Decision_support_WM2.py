import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(layout="wide", page_title="Simulateur Bilan Hydrique V18")

st.title("💧 Simulateur Bilan Hydrique V18 (Flexible)")
tab1, tab2 = st.tabs(["🌊 Bilan Hydrique", "⛈️ Gestion des Crues (IDF)"])

with tab1:
    st.markdown("---")

    # ==========================================
    # 1. PARAMÈTRES (SIDEBAR)
    # ==========================================
    with st.sidebar:
        st.header("1. Paramètres Site")
        
        # --- Données Physiques ---
        vol_min = st.number_input("Volume min. hiver (m³)", value=91712)
        seuil_debordement = st.number_input("Seuil Débordement (m³)", value=330000)
        capacite_traitement = st.number_input("Traitement Max (m³/jour)", value=5000)
        
        # --- Données Bassin ---
        surface_bv = st.number_input("Surface Bassin Versant (m²)", value=1700000)
        surface_plan_eau = st.number_input("Surface Plan d'Eau (m²)", value=20000)
        coeff_ruissellement = st.slider("Coeff. Ruissellement", 0.0, 1.0, 0.85)
        
        # --- Flux d'eau (Entrées / Sorties) ---
        st.markdown("---")
        autres_apports = st.number_input("Autre apport d'eau (m³/jour)", value=0, help="Ex: Pompage depuis une autre fosse")
        
        # MODIFICATION ICI : Changement du nom
        autres_pertes = st.number_input("Autres pertes (m³/jour)", value=452, help="Ex: Concentrateur, Infiltrations, etc.")
        
        # --- Gestion Période Traitement ---
        st.markdown("---")
        mois_options = {
            "Janvier": 1, "Février": 2, "Mars": 3, "Avril": 4, "Mai": 5, "Juin": 6,
            "Juillet": 7, "Août": 8, "Septembre": 9, "Octobre": 10, "Novembre": 11, "Décembre": 12
        }
        col1, col2 = st.columns(2)
        with col1:
            debut_trait_nom = st.selectbox("Début Traitement", list(mois_options.keys()), index=3)
        with col2:
            fin_trait_nom = st.selectbox("Fin Traitement", list(mois_options.keys()), index=10)
        
        debut_trait = mois_options[debut_trait_nom]
        fin_trait = mois_options[fin_trait_nom]

        # ==========================================
        # 2. MÉTÉO ÉDITABLE
        # ==========================================
        st.header("2. Météo & Scénarios")
        
        # Facteurs globaux
        majoration_pluie = st.slider("Ajustement Global Pluie (%)", -50, 50, 0, help="Augmente ou diminue la pluie de tous les mois")
        
        # Données par défaut
        default_data = {
            "Mois": ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"],
            "Pluie (mm)": [43.0, 30.2, 41.0, 46.7, 67.5, 86.4, 105.1, 85.8, 94.4, 75.0, 60.7, 46.2],
            "Evap (mm/j)": [0.0, 0.0, 0.0, 1.0, 3.0, 4.5, 4.5, 3.5, 2.0, 1.0, 0.0, 0.0]
        }
        df_meteo_base = pd.DataFrame(default_data)
        
        with st.expander("📝 Modifier la météo mensuelle", expanded=False):
            st.caption("Modifie les valeurs directement dans ce tableau :")
            edited_meteo = st.data_editor(
                df_meteo_base,
                column_config={
                    "Pluie (mm)": st.column_config.NumberColumn(format="%.1f"),
                    "Evap (mm/j)": st.column_config.NumberColumn(format="%.1f")
                },
                hide_index=True,
                num_rows="fixed"
            )

        # Récupération des données
        facteur_pluie = 1 + (majoration_pluie / 100)
        MOYENNES_PLUIE = edited_meteo["Pluie (mm)"].values * facteur_pluie
        MOYENNES_EVAP = edited_meteo["Evap (mm/j)"].values

    # ==========================================
    # 3. MOTEUR DE SIMULATION
    # ==========================================
    def run_simulation(years=60):
        start_date = pd.to_datetime("2024-01-01")
        dates = pd.date_range(start=start_date, periods=years*365, freq="D")
        n_days = len(dates)
        
        months_idx = dates.month - 1
        
        # Génération Stochastique
        daily_avg_rain = np.array([MOYENNES_PLUIE[m] / 30.0 for m in months_idx])
        pluie_simulee_mm = np.random.exponential(scale=daily_avg_rain, size=n_days)
        evap_simulee_mm = np.array([MOYENNES_EVAP[m] for m in months_idx])
        
        vol_eau = np.zeros(n_days)
        vol_traite = np.zeros(n_days)
        current_vol = vol_min 
        overflow_count = 0
        
        for i in range(n_days):
            m = months_idx[i] + 1
            
            # 1. Calcul des Flux
            vol_pluie_bv = (pluie_simulee_mm[i] / 1000.0) * surface_bv * coeff_ruissellement
            vol_pluie_directe = (pluie_simulee_mm[i] / 1000.0) * surface_plan_eau
            vol_evap = (evap_simulee_mm[i] / 1000.0) * surface_plan_eau
            
            # Sorties fixes (Renommé ici aussi)
            vol_pertes = autres_pertes
            
            # 2. Bilan AVANT traitement
            # (Entrées + Autre Apport) - (Evap + Autres Pertes)
            current_vol = current_vol + vol_pluie_bv + vol_pluie_directe + autres_apports - vol_evap - vol_pertes
            
            # 3. Traitement
            traitement_jour = 0
            if debut_trait <= m <= fin_trait:
                surplus = max(0, current_vol - vol_min)
                traitement_jour = min(capacite_traitement, surplus)
            
            current_vol -= traitement_jour
            
            if current_vol < 0: current_vol = 0
            if current_vol > seuil_debordement: overflow_count += 1
                
            vol_eau[i] = current_vol
            vol_traite[i] = traitement_jour
            
        return pd.DataFrame({"Date": dates, "Volume": vol_eau, "Traitement": vol_traite}), overflow_count

    # ==========================================
    # 4. INTERFACE PRINCIPALE
    # ==========================================

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        launch = st.button("🚀 Lancer Simulation (60 ans)", type="primary")

    if launch:
        with st.spinner('Calcul en cours...'):
            df_res, jours_debord = run_simulation(years=60)
            
            # KPIs
            vol_max = df_res["Volume"].max()
            vol_total_traite = df_res["Traitement"].sum()
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Volume Max", f"{vol_max:,.0f} m³".replace(",", " "), delta_color="inverse")
            k2.metric("Eau Traitée Total", f"{vol_total_traite/1e6:.2f} M m³")
            k3.metric("Autres Apports (Total)", f"{(autres_apports*365*60)/1e6:.1f} M m³")
            k4.metric("Jours Débordement", f"{jours_debord}", delta_color="inverse" if jours_debord > 0 else "normal")
            
            # Graphique
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_res["Date"], y=df_res["Volume"], mode='lines', name='Volume', line=dict(color='#3498db')))
            fig.add_hline(y=seuil_debordement, line_dash="dash", line_color="red", annotation_text="Débordement")
            fig.add_hline(y=vol_min, line_dash="dot", line_color="orange", annotation_text="Min Hiver")
            fig.update_layout(height=500, template="plotly_white", hovermode="x unified", title="Évolution du Volume")
            st.plotly_chart(fig, use_container_width=True)

    # Monte Carlo
    st.markdown("---")
    st.header("🎲 Stress Test (Monte Carlo)")

    if st.button("Lancer l'analyse de risques (10 ans)"):
        bar = st.progress(0)
        all_sims = []
        N_SIMS = 50
        
        for n in range(N_SIMS):
            df_sim, _ = run_simulation(years=10)
            all_sims.append(df_sim["Volume"].values)
            bar.progress((n+1)/N_SIMS)
            
        matrix = np.array(all_sims)
        min_c = np.percentile(matrix, 5, axis=0)
        max_c = np.percentile(matrix, 95, axis=0)
        avg_c = np.mean(matrix, axis=0)
        dates_short = pd.date_range(start="2024-01-01", periods=len(avg_c), freq="D")
        
        fig_mc = go.Figure()
        fig_mc.add_trace(go.Scatter(x=np.concatenate([dates_short, dates_short[::-1]]), y=np.concatenate([max_c, min_c[::-1]]), fill='toself', fillcolor='rgba(100,100,100,0.2)', line=dict(color='rgba(0,0,0,0)'), name='Zone 95%'))
        fig_mc.add_trace(go.Scatter(x=dates_short, y=avg_c, line=dict(color='blue'), name='Moyenne'))
        fig_mc.add_hline(y=seuil_debordement, line_color="red", line_dash="dash")
        fig_mc.update_layout(title=f"Projection Risques (Scénario Pluie {majoration_pluie:+d}%)", height=500, template="plotly_white")
        st.plotly_chart(fig_mc, use_container_width=True)

    # --- CODE TIROIR 2 ---
with tab2:
   with tab2:
    st.header("⛈️ Calculs Hydrauliques Complets (Débit Pointe + Volume 24h)")
    st.markdown("Ce module calcule simultanément le **Débit de pointe** (selon la durée choisie) et le **Volume de gestion** (basé sur une pluie de 24h).")

    # --- 1. CONFIGURATION DE LA PLUIE (TABLE IDF) ---
    st.subheader("1. Table IDF (Intensités en mm/h)")
    
    # J'ai ajouté la ligne 1440 minutes (24h) pour le calcul de volume
    data_idf = {
        "2 ans": [104, 76, 54, 42, 35, 22, 2.5],
        "5 ans": [140, 105, 75, 58, 48, 30, 3.5],
        "10 ans": [165, 124, 88, 68, 56, 36, 4.2],
        "25 ans": [195, 150, 110, 85, 70, 45, 5.0],
        "100 ans": [235, 180, 130, 100, 85, 55, 6.5]
    }
    # Index avec 1440 minutes (24h) à la fin
    df_idf_default = pd.DataFrame(data_idf, index=[5, 10, 15, 30, 60, 120, 1440])
    df_idf_default.index.name = "Durée (min)"

    with st.expander("Voir / Modifier la table IDF", expanded=True):
        st.caption("Assurez-vous d'avoir une ligne '1440' (24h) pour le calcul du volume.")
        edited_idf = st.data_editor(df_idf_default, use_container_width=True)

    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        choix_T = st.selectbox("Période de retour (T)", edited_idf.columns, index=2) # Par défaut 10 ans
    with col_sel2:
        # On exclut 1440 de la sélection par défaut pour le débit de pointe car c'est rare qu'on dimensionne un tuyau sur 24h
        options_duree = [d for d in edited_idf.index if d != 1440]
        if not options_duree: options_duree = edited_idf.index # Sécurité si l'utilisateur efface tout
        
        choix_Duree = st.selectbox("Durée pour Débit de Pointe (minutes)", options_duree, index=2)

    # --- RÉCUPÉRATION DES INTENSITÉS ---
    try:
        # 1. Intensité pour le Débit de Pointe (Durée choisie)
        i_pointe = edited_idf.loc[choix_Duree, choix_T]
        
        # 2. Intensité pour le Volume 24h (On cherche la ligne 1440)
        if 1440 in edited_idf.index:
            i_24h = edited_idf.loc[1440, choix_T]
            msg_vol = f"Basé sur l'intensité 24h : **{i_24h} mm/h**"
        else:
            i_24h = 0
            msg_vol = "⚠️ Ligne 1440 min manquante dans le tableau IDF"

        st.info(f"🌧️ Calculs basés sur : Pointe = **{i_pointe} mm/h** ({choix_Duree} min) | Volume = {msg_vol}")
        
    except Exception as e:
        st.error(f"Erreur de lecture du tableau : {e}")
        i_pointe, i_24h = 0, 0

    st.markdown("---")

    # --- 2. CONFIGURATION DES SURFACES ---
    st.subheader("2. Liste des surfaces drainées")
    
    data_bassins = [
        {"Description": "Toiture Usine", "Surface (ha)": 1.5, "Coeff C": 0.95},
        {"Description": "Stationnement", "Surface (ha)": 0.8, "Coeff C": 0.90},
        {"Description": "Zone Gazonnée", "Surface (ha)": 2.5, "Coeff C": 0.25},
    ]
    df_bassins = pd.DataFrame(data_bassins)
    edited_bassins = st.data_editor(df_bassins, num_rows="dynamic", use_container_width=True)

    # --- 3. RÉSULTATS HYBRIDES ---
    st.markdown("---")
    st.subheader("3. Tableau de Bord Hydrologique")

    if i_pointe > 0 and not edited_bassins.empty:
        resultats = edited_bassins.copy()

        # A. CALCUL DÉBIT DE POINTE (Q = CIA / 360)
        # Utilise l'intensité de la durée courte (ex: 15 min)
        resultats["Q Pointe (m³/s)"] = (resultats["Surface (ha)"] * resultats["Coeff C"] * i_pointe) / 360

        # B. CALCUL VOLUME 24H
        # Formule : Surface (m2) * C * Pluie_24h (m)
        # Ha -> m2 : * 10 000
        # mm/h -> m/24h : (i_24h * 24) / 1000
        # Simplifié : Vol = Surface(ha) * C * i_24h * 240
        if i_24h > 0:
            resultats["Vol. 24h (m³)"] = resultats["Surface (ha)"] * resultats["Coeff C"] * i_24h * 240
        else:
            resultats["Vol. 24h (m³)"] = 0

        # Affichage propre
        st.dataframe(
            resultats.style.format({
                "Surface (ha)": "{:.2f}", 
                "Coeff C": "{:.2f}",
                "Q Pointe (m³/s)": "{:.3f}",
                "Vol. 24h (m³)": "{:.0f}"
            }), 
            use_container_width=True
        )

        # TOTAUX
        c1, c2, c3 = st.columns(3)
        c1.metric("Surface Totale", f"{resultats['Surface (ha)'].sum():.2f} ha")
        
        # Somme des débits de pointe (Hypothèse conservative : pics simultanés)
        q_total = resultats["Q Pointe (m³/s)"].sum()
        c2.metric(f"🌊 Débit Pointe Total ({choix_Duree} min)", f"{q_total:.3f} m³/s")
        
        # Somme des volumes 24h
        v_total = resultats["Vol. 24h (m³)"].sum()
        c3.metric(f"💧 Volume à gérer (24h)", f"{v_total:.0f} m³", delta_color="inverse")

    else:
        st.warning("Veuillez vérifier les données d'entrée.")