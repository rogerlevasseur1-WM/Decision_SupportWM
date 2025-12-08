import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(layout="wide", page_title="Simulateur Bilan Hydrique V20")

st.title("💧 Simulateur Bilan Hydrique V20 (Neige + Moyennes)")
st.caption("Version finale : Gestion de la fonte + Validation des moyennes annuelles.")
tab1, tab2 = st.tabs(["🌊 Bilan Hydrique", "⛈️ Gestion des Crues (IDF)"])

# ==========================================
# ONGLET 1 : BILAN HYDRIQUE
# ==========================================
with tab1:
    st.markdown("---")

    # 1. PARAMÈTRES (SIDEBAR)
    with st.sidebar:
        st.header("1. Paramètres Site")
        
        # --- Données Physiques ---
        vol_min = st.number_input("Volume min. hiver (m³)", value=91712)
        seuil_debordement = st.number_input("Seuil Débordement (m³)", value=330000)
        # ICI : Il faut mettre la capacité de pointe de la pompe, pas la moyenne
        capacite_traitement = st.number_input("Capacité Pompe Max (m³/jour)", value=5000, help="Mettre la capacité max technique, pas la moyenne annuelle.")
        
        # --- Données Bassin ---
        surface_bv = st.number_input("Surface Bassin Versant (m²)", value=1700000)
        surface_plan_eau = st.number_input("Surface Plan d'Eau (m²)", value=20000)
        coeff_ruissellement = st.slider("Coeff. Ruissellement (Été)", 0.0, 1.0, 0.85)
        
        # --- Paramètres Fonte ---
        st.markdown("❄️ **Paramètres Neige**")
        melt_rate = st.number_input("Coeff. Fonte (mm/°C/jour)", value=4.0, help="Vitesse de fonte par degré au dessus de zéro.")
        
        # --- Flux d'eau ---
        st.markdown("---")
        autres_apports = st.number_input("Autre apport d'eau (m³/jour)", value=0)
        autres_pertes = st.number_input("Autres pertes (m³/jour)", value=452)
        
        # --- Gestion Période Traitement ---
        st.markdown("---")
        mois_options = {
            "Janvier": 1, "Février": 2, "Mars": 3, "Avril": 4, "Mai": 5, "Juin": 6,
            "Juillet": 7, "Août": 8, "Septembre": 9, "Octobre": 10, "Novembre": 11, "Décembre": 12
        }
        col1, col2 = st.columns(2)
        with col1:
            debut_trait_nom = st.selectbox("Début Traitement", list(mois_options.keys()), index=3) # Avril par défaut
        with col2:
            fin_trait_nom = st.selectbox("Fin Traitement", list(mois_options.keys()), index=10) # Novembre par défaut
        
        debut_trait = mois_options[debut_trait_nom]
        fin_trait = mois_options[fin_trait_nom]

        # 2. MÉTÉO ÉDITABLE (Pluie + Température)
        st.header("2. Météo & Scénarios")
        
        majoration_pluie = st.slider("Ajustement Global Pluie (%)", -50, 50, 0)
        
        # Données par défaut (Avec Température Moyenne ajoutée)
        default_data = {
            "Mois": ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"],
            "Pluie (mm)": [43.0, 30.2, 41.0, 46.7, 67.5, 86.4, 105.1, 85.8, 94.4, 75.0, 60.7, 46.2],
            "Evap (mm/j)": [0.0, 0.0, 0.0, 1.0, 3.0, 4.5, 4.5, 3.5, 2.0, 1.0, 0.0, 0.0],
            "Temp (°C)": [-10.0, -8.0, -2.0, 5.0, 12.0, 17.0, 20.0, 19.0, 14.0, 7.0, 0.5, -6.0]
        }
        df_meteo_base = pd.DataFrame(default_data)
        
        with st.expander("📝 Modifier Météo (Pluie & Temp)", expanded=False):
            edited_meteo = st.data_editor(
                df_meteo_base,
                column_config={
                    "Pluie (mm)": st.column_config.NumberColumn(format="%.1f"),
                    "Evap (mm/j)": st.column_config.NumberColumn(format="%.1f"),
                    "Temp (°C)": st.column_config.NumberColumn(format="%.1f")
                },
                hide_index=True,
                num_rows="fixed"
            )

        # Récupération des données
        facteur_pluie = 1 + (majoration_pluie / 100)
        MOYENNES_PLUIE = edited_meteo["Pluie (mm)"].values * facteur_pluie
        MOYENNES_EVAP = edited_meteo["Evap (mm/j)"].values
        MOYENNES_TEMP = edited_meteo["Temp (°C)"].values

    # 3. MOTEUR DE SIMULATION (AVEC NEIGE)
    def run_simulation(years=60):
        start_date = pd.to_datetime("2024-01-01")
        dates = pd.date_range(start=start_date, periods=years*365, freq="D")
        n_days = len(dates)
        
        months_idx = dates.month - 1
        
        # Génération Stochastique des Précipitations
        daily_avg_rain = np.array([MOYENNES_PLUIE[m] / 30.0 for m in months_idx])
        precip_brute_mm = np.random.exponential(scale=daily_avg_rain, size=n_days)
        
        # Génération des Températures (Avec un peu de variation aléatoire +/- 3°C)
        temp_base = np.array([MOYENNES_TEMP[m] for m in months_idx])
        temp_simulee = temp_base + np.random.normal(0, 3, n_days)
        
        evap_simulee_mm = np.array([MOYENNES_EVAP[m] for m in months_idx])
        
        # Tableaux de résultats
        vol_eau = np.zeros(n_days)
        vol_traite = np.zeros(n_days)
        stock_neige = np.zeros(n_days) # Pour le graphique
        
        current_vol = vol_min 
        current_snowpack = 0.0 # Stock de neige au sol en mm d'eau
        overflow_count = 0
        
        for i in range(n_days):
            m = months_idx[i] + 1
            temp_jour = temp_simulee[i]
            precip_jour = precip_brute_mm[i]
            
            # --- LOGIQUE NEIGE / FONTE ---
            eau_liquide_disponible = 0.0
            
            if temp_jour <= 0:
                # C'est de la NEIGE : On stocke, rien ne coule
                current_snowpack += precip_jour
                eau_liquide_disponible = 0.0
            else:
                # C'est de la PLUIE + FONTE
                # 1. La pluie du jour est liquide
                eau_liquide_disponible += precip_jour
                
                # 2. Fonte de la neige accumulée
                # Formule degré-jour : Fonte = T * Rate
                fonte_potentielle = temp_jour * melt_rate
                fonte_reelle = min(current_snowpack, fonte_potentielle)
                
                current_snowpack -= fonte_reelle
                eau_liquide_disponible += fonte_reelle
            
            # Sauvegarde pour graphique
            stock_neige[i] = current_snowpack

            # --- BILAN HYDRIQUE ---
            vol_pluie_bv = (eau_liquide_disponible / 1000.0) * surface_bv * coeff_ruissellement
            vol_pluie_directe = (eau_liquide_disponible / 1000.0) * surface_plan_eau
            vol_evap = (evap_simulee_mm[i] / 1000.0) * surface_plan_eau
            
            # Sorties fixes
            vol_pertes = autres_pertes
            
            # Bilan AVANT traitement
            current_vol = current_vol + vol_pluie_bv + vol_pluie_directe + autres_apports - vol_evap - vol_pertes
            
            # Traitement
            traitement_jour = 0
            if debut_trait <= m <= fin_trait:
                surplus = max(0, current_vol - vol_min)
                traitement_jour = min(capacite_traitement, surplus)
            
            current_vol -= traitement_jour
            
            if current_vol < 0: current_vol = 0
            if current_vol > seuil_debordement: overflow_count += 1
                
            vol_eau[i] = current_vol
            vol_traite[i] = traitement_jour
            
        return pd.DataFrame({
            "Date": dates, 
            "Volume": vol_eau, 
            "Traitement": vol_traite,
            "Neige_Stock_mm": stock_neige
        }), overflow_count

    # 4. INTERFACE PRINCIPALE
    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        launch = st.button("🚀 Lancer Simulation (60 ans)", type="primary")

    if launch:
        with st.spinner('Simulation accumulation neige & fonte en cours...'):
            YEARS_SIM = 60
            df_res, jours_debord = run_simulation(years=YEARS_SIM)
            
            # --- CALCULS KPI AVEC MOYENNE ANNUELLE ---
            vol_max = df_res["Volume"].max()
            vol_total_traite = df_res["Traitement"].sum()
            
            # Calcul de la moyenne par an pour comparer avec Excel
            moyenne_annuelle_traitee = vol_total_traite / YEARS_SIM
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Volume Max Bassin", f"{vol_max:,.0f} m³".replace(",", " "), delta_color="inverse")
            
            # C'est ici le chiffre important pour ta validation
            k2.metric("Moyenne Annuelle Traitée", f"{moyenne_annuelle_traitee:,.0f} m³/an".replace(",", " "), 
                      help="Compare ce chiffre avec la décharge annuelle de ton autre modèle.")
            
            k3.metric("Jours Débordement", f"{jours_debord}", delta_color="inverse" if jours_debord > 0 else "normal")
            k4.metric("Total Traité (60 ans)", f"{vol_total_traite/1e6:.1f} M m³")
            
            # Graphique Double Axe (Volume + Neige)
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # Trace 1 : Volume d'eau (Axe Gauche)
            fig.add_trace(
                go.Scatter(x=df_res["Date"], y=df_res["Volume"], name="Volume Eau (m³)", line=dict(color='#3498db')),
                secondary_y=False
            )
            
            # Trace 2 : Stock Neige (Axe Droit)
            fig.add_trace(
                go.Scatter(x=df_res["Date"], y=df_res["Neige_Stock_mm"], name="Stock Neige (mm)", 
                           line=dict(color='#bdc3c7', width=1), fill='tozeroy', opacity=0.5),
                secondary_y=True
            )

            # Seuils
            fig.add_hline(y=seuil_debordement, line_dash="dash", line_color="red", annotation_text="Débordement", secondary_y=False)
            fig.add_hline(y=vol_min, line_dash="dot", line_color="orange", annotation_text="Min Hiver", secondary_y=False)
            
            fig.update_layout(height=550, title="Volume d'eau vs Accumulation de Neige", hovermode="x unified")
            fig.update_yaxes(title_text="Volume Bassin (m³)", secondary_y=False)
            fig.update_yaxes(title_text="Neige au sol (mm eau)", secondary_y=True, showgrid=False)
            
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
        fig_mc.update_layout(title=f"Projection Risques (Avec Fonte des Neiges)", height=500, template="plotly_white")
        st.plotly_chart(fig_mc, use_container_width=True)


# ==========================================
# ONGLET 2 : IDF & HYDRAULIQUE
# ==========================================
with tab2:
    st.header("⛈️ Calculs Hydrauliques Complets (Débit Pointe + Volume 24h)")
    st.markdown("Ce module calcule simultanément le **Débit de pointe** (selon la durée choisie) et le **Volume de gestion** (basé sur une pluie de 24h).")

    # --- 1. CONFIGURATION DE LA PLUIE (TABLE IDF) ---
    st.subheader("1. Table IDF (Intensités en mm/h)")
    
    # Correction de l'erreur de syntaxe ici :
    data_idf = {
        "2 ans": [104, 76, 54, 42, 35, 22, 2.5],
        "5 ans": [140, 105, 75, 58, 48, 30, 3.5],
        "10 ans": [165, 124, 88, 68, 56, 36, 4.2],
        "25 ans": [195, 150, 110, 85, 70, 45, 5.0],
        "100 ans": [235, 180, 130, 100, 85, 55, 6.5]
    }
    # Index 1440 = 24h
    df_idf_default = pd.DataFrame(data_idf, index=[5, 10, 15, 30, 60, 120, 1440])
    df_idf_default.index.name = "Durée (min)"

    with st.expander("Voir / Modifier la table IDF", expanded=True):
        st.caption("Assurez-vous d'avoir une ligne '1440' (24h) pour le calcul du volume.")
        edited_idf = st.data_editor(df_idf_default, use_container_width=True)

    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        choix_T = st.selectbox("Période de retour (T)", edited_idf.columns, index=2)
    with col_sel2:
        options_duree = [d for d in edited_idf.index if d != 1440]
        if not options_duree: options_duree = edited_idf.index
        choix_Duree = st.selectbox("Durée pour Débit de Pointe (minutes)", options_duree, index=2)

    try:
        i_pointe = edited_idf.loc[choix_Duree, choix_T]
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
        resultats["Q Pointe (m³/s)"] = (resultats["Surface (ha)"] * resultats["Coeff C"] * i_pointe) / 360

        # B. CALCUL VOLUME 24H
        if i_24h > 0:
            resultats["Vol. 24h (m³)"] = resultats["Surface (ha)"] * resultats["Coeff C"] * i_24h * 240
        else:
            resultats["Vol. 24h (m³)"] = 0

        st.dataframe(
            resultats.style.format({
                "Surface (ha)": "{:.2f}", 
                "Coeff C": "{:.2f}",
                "Q Pointe (m³/s)": "{:.3f}",
                "Vol. 24h (m³)": "{:.0f}"
            }), 
            use_container_width=True
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Surface Totale", f"{resultats['Surface (ha)'].sum():.2f} ha")
        
        q_total = resultats["Q Pointe (m³/s)"].sum()
        c2.metric(f"🌊 Débit Pointe Total ({choix_Duree} min)", f"{q_total:.3f} m³/s")
        
        v_total = resultats["Vol. 24h (m³)"].sum()
        c3.metric(f"💧 Volume à gérer (24h)", f"{v_total:.0f} m³", delta_color="inverse")

    else:
        st.warning("Veuillez vérifier les données d'entrée.")