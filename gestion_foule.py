import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
from PIL import Image, ImageTk
import numpy as np
import threading
import time
from datetime import datetime
import json
import os
from ultralytics import YOLO
import pygame

class SystemeGestionFoule:
    def __init__(self, root):
        self.root = root
        self.root.title("Système de Gestion de Foule - Stade")
        self.root.geometry("1400x900")
        self.root.configure(bg='#2c3e50')
        
        # Variables de contrôle
        self.video_active = False
        self.cap = None
        self.model_yolo = None
        self.model_weapons = None
        
        # Paramètres de détection
        self.seuil_foule_danger = 50  # Nombre de personnes considéré dangereux
        self.temps_surveillance = 10  # Secondes avant alarme
        self.compteur_temps_foule = 0
        self.derniere_detection = time.time()
        
        # Compteurs
        self.nombre_personnes = 0
        self.historique_personnes = []
        self.alerte_foule_active = False
        self.alerte_arme_active = False
        
        # Initialiser pygame pour les alarmes sonores
        pygame.mixer.init()
        
        self.creer_interface()
        self.charger_modeles()
        
    def creer_interface(self):
        # Titre principal
        titre = tk.Label(self.root, text="🏟️ SYSTÈME DE GESTION DE FOULE", 
                        font=('Arial', 20, 'bold'), fg='white', bg='#2c3e50')
        titre.pack(pady=10)
        
        # Frame principal
        main_frame = tk.Frame(self.root, bg='#2c3e50')
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Frame de gauche - Vidéo et contrôles
        left_frame = tk.Frame(main_frame, bg='#34495e', relief='raised', bd=2)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        # Zone d'affichage vidéo
        self.video_label = tk.Label(left_frame, text="📹 Sélectionnez une source vidéo", 
                                   font=('Arial', 16), bg='#34495e', fg='white')
        self.video_label.pack(pady=20)
        
        # Contrôles vidéo
        controles_frame = tk.Frame(left_frame, bg='#34495e')
        controles_frame.pack(pady=10)
        
        self.btn_fichier = tk.Button(controles_frame, text="📁 Choisir Fichier Vidéo", 
                                    command=self.choisir_fichier_video, bg='#3498db', fg='white',
                                    font=('Arial', 10, 'bold'), padx=20, pady=5)
        self.btn_fichier.pack(side='left', padx=5)
        
        self.btn_camera = tk.Button(controles_frame, text="📷 Utiliser Caméra", 
                                   command=self.utiliser_camera, bg='#27ae60', fg='white',
                                   font=('Arial', 10, 'bold'), padx=20, pady=5)
        self.btn_camera.pack(side='left', padx=5)
        
        self.btn_arreter = tk.Button(controles_frame, text="⏹️ Arrêter", 
                                    command=self.arreter_video, bg='#e74c3c', fg='white',
                                    font=('Arial', 10, 'bold'), padx=20, pady=5)
        self.btn_arreter.pack(side='left', padx=5)
        
        # Frame de droite - Dashboard et alertes
        right_frame = tk.Frame(main_frame, bg='#34495e', relief='raised', bd=2)
        right_frame.pack(side='right', fill='y', padx=(5, 0))
        right_frame.configure(width=400)
        
        # Dashboard
        dashboard_label = tk.Label(right_frame, text="📊 TABLEAU DE BORD", 
                                  font=('Arial', 16, 'bold'), fg='white', bg='#34495e')
        dashboard_label.pack(pady=(10, 20))
        
        # Compteur de personnes
        self.compteur_frame = tk.Frame(right_frame, bg='#2ecc71', relief='raised', bd=3)
        self.compteur_frame.pack(pady=10, padx=20, fill='x')
        
        tk.Label(self.compteur_frame, text="👥 NOMBRE DE PERSONNES", 
                font=('Arial', 12, 'bold'), bg='#2ecc71', fg='white').pack(pady=5)
        
        self.label_nombre = tk.Label(self.compteur_frame, text="0", 
                                    font=('Arial', 36, 'bold'), bg='#2ecc71', fg='white')
        self.label_nombre.pack(pady=10)
        
        # État de sécurité
        self.etat_frame = tk.Frame(right_frame, bg='#2ecc71', relief='raised', bd=3)
        self.etat_frame.pack(pady=10, padx=20, fill='x')
        
        tk.Label(self.etat_frame, text="🛡️ ÉTAT DE SÉCURITÉ", 
                font=('Arial', 12, 'bold'), bg='#2ecc71', fg='white').pack(pady=5)
        
        self.label_etat = tk.Label(self.etat_frame, text="✅ SÉCURISÉ", 
                                  font=('Arial', 16, 'bold'), bg='#2ecc71', fg='white')
        self.label_etat.pack(pady=10)
        
        # Alertes
        alertes_label = tk.Label(right_frame, text="🚨 SYSTÈME D'ALERTES", 
                                font=('Arial', 16, 'bold'), fg='white', bg='#34495e')
        alertes_label.pack(pady=(30, 10))
        
        # Alerte foule
        self.alerte_foule_frame = tk.Frame(right_frame, bg='#f39c12', relief='raised', bd=3)
        self.alerte_foule_frame.pack(pady=10, padx=20, fill='x')
        
        self.label_alerte_foule = tk.Label(self.alerte_foule_frame, text="⚠️ GESTION DE FOULE\nNORMALE", 
                                          font=('Arial', 12, 'bold'), bg='#f39c12', fg='white')
        self.label_alerte_foule.pack(pady=15)
        
        # Alerte arme
        self.alerte_arme_frame = tk.Frame(right_frame, bg='#95a5a6', relief='raised', bd=3)
        self.alerte_arme_frame.pack(pady=10, padx=20, fill='x')
        
        self.label_alerte_arme = tk.Label(self.alerte_arme_frame, text="🔒 DÉTECTION D'ARMES\nINACTIVE", 
                                         font=('Arial', 12, 'bold'), bg='#95a5a6', fg='white')
        self.label_alerte_arme.pack(pady=15)
        
        # Paramètres
        params_label = tk.Label(right_frame, text="⚙️ PARAMÈTRES", 
                               font=('Arial', 14, 'bold'), fg='white', bg='#34495e')
        params_label.pack(pady=(30, 10))
        
        # Seuil de foule
        seuil_frame = tk.Frame(right_frame, bg='#34495e')
        seuil_frame.pack(pady=5, padx=20, fill='x')
        
        tk.Label(seuil_frame, text="Seuil foule dangereuse:", 
                font=('Arial', 10), fg='white', bg='#34495e').pack(anchor='w')
        
        self.seuil_var = tk.StringVar(value=str(self.seuil_foule_danger))
        seuil_entry = tk.Entry(seuil_frame, textvariable=self.seuil_var, width=10)
        seuil_entry.pack(anchor='w', pady=2)
        seuil_entry.bind('<Return>', self.mettre_a_jour_seuil)
        
        # Temps de surveillance
        temps_frame = tk.Frame(right_frame, bg='#34495e')
        temps_frame.pack(pady=5, padx=20, fill='x')
        
        tk.Label(temps_frame, text="Temps surveillance (s):", 
                font=('Arial', 10), fg='white', bg='#34495e').pack(anchor='w')
        
        self.temps_var = tk.StringVar(value=str(self.temps_surveillance))
        temps_entry = tk.Entry(temps_frame, textvariable=self.temps_var, width=10)
        temps_entry.pack(anchor='w', pady=2)
        temps_entry.bind('<Return>', self.mettre_a_jour_temps)
        
        # Historique
        self.historique_text = tk.Text(right_frame, height=8, width=40, bg='#2c3e50', fg='white')
        self.historique_text.pack(pady=10, padx=20, fill='x')
        
    def charger_modeles(self):
        """Charge les modèles YOLO"""
        try:
            # Modèle pour détection de personnes (YOLO standard)
            self.model_yolo = YOLO('yolov8n.pt')  # Modèle léger pour personnes
            self.ajouter_log("✅ Modèle YOLO chargé avec succès")
            
            # Pour la détection d'armes, vous devrez entraîner un modèle spécialisé
            # ou utiliser un modèle pré-entraîné pour objets dangereux
            try:
                self.model_weapons = YOLO('yolov8n.pt')  # Remplacer par modèle d'armes
                self.ajouter_log("✅ Modèle détection d'armes chargé")
            except:
                self.ajouter_log("⚠️ Modèle détection d'armes non disponible")
                
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du chargement des modèles: {str(e)}")
            self.ajouter_log(f"❌ Erreur chargement modèles: {str(e)}")
    
    def choisir_fichier_video(self):
        """Sélectionne un fichier vidéo"""
        fichier = filedialog.askopenfilename(
            title="Choisir fichier vidéo",
            filetypes=[("Fichiers vidéo", "*.mp4 *.avi *.mov *.mkv")]
        )
        if fichier:
            self.demarrer_detection_video(fichier)
    
    def utiliser_camera(self):
        """Utilise la caméra par défaut"""
        self.demarrer_detection_video(0)
    
    def demarrer_detection_video(self, source):
        """Démarre la détection sur la source vidéo"""
        if self.video_active:
            self.arreter_video()
        
        try:
            self.cap = cv2.VideoCapture(source)
            if not self.cap.isOpened():
                raise Exception("Impossible d'ouvrir la source vidéo")
            
            self.video_active = True
            self.ajouter_log(f"📹 Détection démarrée - Source: {source}")
            
            # Démarrer le thread de traitement
            self.thread_video = threading.Thread(target=self.traiter_video)
            self.thread_video.daemon = True
            self.thread_video.start()
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du démarrage: {str(e)}")
    
    def arreter_video(self):
        """Arrête la détection vidéo"""
        self.video_active = False
        if self.cap:
            self.cap.release()
        self.ajouter_log("⏹️ Détection arrêtée")
        self.video_label.config(text="📹 Sélectionnez une source vidéo")
    
    def traiter_video(self):
        """Traite la vidéo frame par frame"""
        while self.video_active:
            ret, frame = self.cap.read()
            if not ret:
                break
            
            # Redimensionner pour l'affichage
            frame = cv2.resize(frame, (640, 480))
            
            # Détection avec YOLO
            if self.model_yolo:
                frame_traite = self.detecter_objets(frame)
            else:
                frame_traite = frame
            
            # Afficher la frame
            self.afficher_frame(frame_traite)
            
            # Vérifier les alertes
            self.verifier_alertes()
            
            time.sleep(0.03)  # ~30 FPS
    
    def detecter_objets(self, frame):
        """Détecte les personnes et objets dangereux"""
        frame_resultat = frame.copy()
        
        try:
            # Détection des personnes
            resultats = self.model_yolo(frame, conf=0.5)
            
            personnes_detectees = 0
            armes_detectees = False
            
            for resultat in resultats:
                boxes = resultat.boxes
                if boxes is not None:
                    for box in boxes:
                        # Coordonnées de la boîte
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        conf = float(box.conf[0])
                        cls = int(box.cls[0])
                        
                        # Noms des classes COCO
                        noms_classes = self.model_yolo.names
                        nom_classe = noms_classes[cls]
                        
                        # Détecter les personnes
                        if nom_classe == 'person' and conf > 0.5:
                            personnes_detectees += 1
                            cv2.rectangle(frame_resultat, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(frame_resultat, f'Personne {conf:.2f}', 
                                       (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                        
                        # Détecter objets potentiellement dangereux
                        objets_dangereux = ['knife', 'scissors', 'bottle', 'baseball bat']
                        if nom_classe in objets_dangereux and conf > 0.3:
                            armes_detectees = True
                            cv2.rectangle(frame_resultat, (x1, y1), (x2, y2), (0, 0, 255), 3)
                            cv2.putText(frame_resultat, f'DANGER: {nom_classe}', 
                                       (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Mettre à jour les compteurs
            self.nombre_personnes = personnes_detectees
            self.historique_personnes.append({
                'temps': datetime.now().strftime("%H:%M:%S"),
                'personnes': personnes_detectees,
                'armes': armes_detectees
            })
            
            # Garder seulement les 100 dernières entrées
            if len(self.historique_personnes) > 100:
                self.historique_personnes.pop(0)
            
            # Afficher les statistiques sur l'image
            cv2.putText(frame_resultat, f'Personnes: {personnes_detectees}', 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            if armes_detectees:
                cv2.putText(frame_resultat, 'ALERTE ARME DETECTEE!', 
                           (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                self.alerte_arme_active = True
            else:
                self.alerte_arme_active = False
                
        except Exception as e:
            self.ajouter_log(f"❌ Erreur détection: {str(e)}")
        
        return frame_resultat
    
    def afficher_frame(self, frame):
        """Affiche la frame dans l'interface"""
        try:
            # Convertir BGR vers RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Convertir en image PIL puis PhotoImage
            img_pil = Image.fromarray(frame_rgb)
            img_tk = ImageTk.PhotoImage(img_pil)
            
            # Mettre à jour le label
            self.video_label.config(image=img_tk, text="")
            self.video_label.image = img_tk  # Garder une référence
            
        except Exception as e:
            self.ajouter_log(f"❌ Erreur affichage: {str(e)}")
    
    def verifier_alertes(self):
        """Vérifie et gère les alertes"""
        # Mettre à jour l'affichage du nombre de personnes
        self.root.after(0, lambda: self.label_nombre.config(text=str(self.nombre_personnes)))
        
        # Vérifier alerte foule
        if self.nombre_personnes >= self.seuil_foule_danger:
            if not self.alerte_foule_active:
                # Première détection de foule dangereuse
                self.compteur_temps_foule = time.time()
                self.alerte_foule_active = True
                self.root.after(0, self.activer_alerte_foule_warning)
            else:
                # Vérifier si la foule persiste
                if time.time() - self.compteur_temps_foule >= self.temps_surveillance:
                    self.root.after(0, self.activer_alerte_foule_danger)
        else:
            if self.alerte_foule_active:
                self.alerte_foule_active = False
                self.root.after(0, self.desactiver_alerte_foule)
        
        # Vérifier alerte arme
        if self.alerte_arme_active:
            self.root.after(0, self.activer_alerte_arme)
        else:
            self.root.after(0, self.desactiver_alerte_arme)
    
    def activer_alerte_foule_warning(self):
        """Active l'alerte foule en mode warning"""
        self.alerte_foule_frame.config(bg='#f39c12')
        self.label_alerte_foule.config(
            text=f"⚠️ FOULE DÉTECTÉE\n{self.nombre_personnes} personnes\nSURVEILLANCE...",
            bg='#f39c12'
        )
        self.compteur_frame.config(bg='#f39c12')
        self.label_nombre.config(bg='#f39c12')
        self.etat_frame.config(bg='#f39c12')
        self.label_etat.config(text="⚠️ SURVEILLANCE", bg='#f39c12')
    
    def activer_alerte_foule_danger(self):
        """Active l'alerte foule en mode danger"""
        self.alerte_foule_frame.config(bg='#e74c3c')
        self.label_alerte_foule.config(
            text=f"🚨 ALERTE FOULE!\n{self.nombre_personnes} personnes\nDANGER!",
            bg='#e74c3c'
        )
        self.compteur_frame.config(bg='#e74c3c')
        self.label_nombre.config(bg='#e74c3c')
        self.etat_frame.config(bg='#e74c3c')
        self.label_etat.config(text="🚨 DANGER", bg='#e74c3c')
        
        # Jouer alarme sonore (optionnel)
        try:
            # Créer un son d'alarme simple
            duration = 0.5
            freq = 800
            sample_rate = 22050
            frames = int(duration * sample_rate)
            arr = np.zeros(frames)
            for i in range(frames):
                arr[i] = np.sin(2 * np.pi * freq * i / sample_rate)
            arr = (arr * 32767).astype(np.int16)
            sound = pygame.sndarray.make_sound(np.column_stack((arr, arr)))
            sound.play()
        except:
            pass
        
        self.ajouter_log(f"🚨 ALERTE FOULE ACTIVÉE - {self.nombre_personnes} personnes détectées")
    
    def desactiver_alerte_foule(self):
        """Désactive l'alerte foule"""
        self.alerte_foule_frame.config(bg='#2ecc71')
        self.label_alerte_foule.config(
            text="✅ GESTION DE FOULE\nNORMALE",
            bg='#2ecc71'
        )
        self.compteur_frame.config(bg='#2ecc71')
        self.label_nombre.config(bg='#2ecc71')
        self.etat_frame.config(bg='#2ecc71')
        self.label_etat.config(text="✅ SÉCURISÉ", bg='#2ecc71')
        
        self.ajouter_log("✅ Alerte foule désactivée - Situation normale")
    
    def activer_alerte_arme(self):
        """Active l'alerte arme"""
        self.alerte_arme_frame.config(bg='#e74c3c')
        self.label_alerte_arme.config(
            text="🚨 ARME DÉTECTÉE!\nURGENCE!",
            bg='#e74c3c'
        )
        
        if not hasattr(self, 'derniere_alerte_arme') or time.time() - self.derniere_alerte_arme > 5:
            self.ajouter_log("🚨 URGENCE - ARME DÉTECTÉE!")
            self.derniere_alerte_arme = time.time()
            
            # Alarme sonore d'urgence
            try:
                for _ in range(3):
                    duration = 0.3
                    freq = 1000
                    sample_rate = 22050
                    frames = int(duration * sample_rate)
                    arr = np.zeros(frames)
                    for i in range(frames):
                        arr[i] = np.sin(2 * np.pi * freq * i / sample_rate)
                    arr = (arr * 32767).astype(np.int16)
                    sound = pygame.sndarray.make_sound(np.column_stack((arr, arr)))
                    sound.play()
                    time.sleep(0.1)
            except:
                pass
    
    def desactiver_alerte_arme(self):
        """Désactive l'alerte arme"""
        self.alerte_arme_frame.config(bg='#95a5a6')
        self.label_alerte_arme.config(
            text="🔒 DÉTECTION D'ARMES\nNORMALE",
            bg='#95a5a6'
        )
    
    def mettre_a_jour_seuil(self, event=None):
        """Met à jour le seuil de foule dangereuse"""
        try:
            nouveau_seuil = int(self.seuil_var.get())
            self.seuil_foule_danger = nouveau_seuil
            self.ajouter_log(f"⚙️ Seuil foule mis à jour: {nouveau_seuil}")
        except ValueError:
            messagebox.showerror("Erreur", "Seuil invalide")
    
    def mettre_a_jour_temps(self, event=None):
        """Met à jour le temps de surveillance"""
        try:
            nouveau_temps = int(self.temps_var.get())
            self.temps_surveillance = nouveau_temps
            self.ajouter_log(f"⚙️ Temps surveillance mis à jour: {nouveau_temps}s")
        except ValueError:
            messagebox.showerror("Erreur", "Temps invalide")
    
    def ajouter_log(self, message):
        """Ajoute un message au log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        def update_text():
            self.historique_text.insert(tk.END, log_message)
            self.historique_text.see(tk.END)
            
            # Limiter le nombre de lignes
            lines = self.historique_text.get("1.0", tk.END).split('\n')
            if len(lines) > 50:
                self.historique_text.delete("1.0", "2.0")
        
        if threading.current_thread() != threading.main_thread():
            self.root.after(0, update_text)
        else:
            update_text()

def main():
    root = tk.Tk()
    app = SystemeGestionFoule(root)
    
    def on_closing():
        app.arreter_video()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()