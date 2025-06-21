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
import collections
import shutil

class CentroidTracker:
    def __init__(self, max_disappeared=40):
        self.nextObjectID = 0
        self.objects = collections.OrderedDict()
        self.disappeared = collections.OrderedDict()
        self.max_disappeared = max_disappeared

    def register(self, centroid):
        self.objects[self.nextObjectID] = centroid
        self.disappeared[self.nextObjectID] = 0
        self.nextObjectID += 1

    def deregister(self, objectID):
        del self.objects[objectID]
        del self.disappeared[objectID]

    def update(self, rects):
        if len(rects) == 0:
            for objectID in list(self.disappeared.keys()):
                self.disappeared[objectID] += 1
                if self.disappeared[objectID] > self.max_disappeared:
                    self.deregister(objectID)
            return self.objects
        input_centroids = np.zeros((len(rects), 2), dtype="int")
        for (i, (startX, startY, endX, endY)) in enumerate(rects):
            cX = int((startX + endX) / 2.0)
            cY = int((startY + endY) / 2.0)
            input_centroids[i] = (cX, cY)
        if len(self.objects) == 0:
            for i in range(0, len(input_centroids)):
                self.register(input_centroids[i])
        else:
            objectIDs = list(self.objects.keys())
            objectCentroids = list(self.objects.values())
            D = np.linalg.norm(np.array(objectCentroids)[:, np.newaxis] - input_centroids, axis=2)
            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]
            usedRows = set()
            usedCols = set()
            for (row, col) in zip(rows, cols):
                if row in usedRows or col in usedCols:
                    continue
                objectID = objectIDs[row]
                self.objects[objectID] = input_centroids[col]
                self.disappeared[objectID] = 0
                usedRows.add(row)
                usedCols.add(col)
            unusedRows = set(range(0, D.shape[0])).difference(usedRows)
            unusedCols = set(range(0, D.shape[1])).difference(usedCols)
            if D.shape[0] >= D.shape[1]:
                for row in unusedRows:
                    objectID = objectIDs[row]
                    self.disappeared[objectID] += 1
                    if self.disappeared[objectID] > self.max_disappeared:
                        self.deregister(objectID)
            else:
                for col in unusedCols:
                    self.register(input_centroids[col])
        return self.objects

class SystemeGestionFoule:
    def __init__(self, root):
        self.root = root
        self.root.title("Système de Gestion de Foule - Stade")
        self.root.geometry("1400x980")
        self.root.configure(bg='#2c3e50')
        
        # Clean and recreate dangerous_persons folder
        dangerous_folder = 'dangerous_persons'
        if os.path.exists(dangerous_folder):
            shutil.rmtree(dangerous_folder)
        os.makedirs(dangerous_folder, exist_ok=True)
        
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
        self.types_armes_courantes = []  # Liste des types d'armes détectées
        
        # Initialiser pygame pour les alarmes sonores
        pygame.mixer.init()
        
        self.person_tracker = CentroidTracker()
        self.person_entry_times = {}  # {id: first_seen_time}
        self.worker_ids = set()  # IDs of workers to ignore
        self.current_ids = set()
        
        self.creer_interface()
        self.charger_modeles()
        
    def creer_interface(self):
        # Frame pour le logo et titre
        header_frame = tk.Frame(self.root, bg='#2c3e50')
        header_frame.pack(fill='x', padx=10, pady=5)
        
        # Charger et afficher le logo
        try:
            logo_img = Image.open("logo.jpg")
            # Redimensionner le logo pour qu'il soit approprié
            logo_img = logo_img.resize((80, 80), Image.Resampling.LANCZOS)
            logo_photo = ImageTk.PhotoImage(logo_img)
            
            logo_label = tk.Label(header_frame, image=logo_photo, bg='#2c3e50')
            logo_label.image = logo_photo  # Garder une référence
            logo_label.pack(side='left', padx=(0, 10))
        except Exception as e:
            print(f"Erreur lors du chargement du logo: {e}")
            # Si le logo ne peut pas être chargé, créer un placeholder
            logo_label = tk.Label(header_frame, text="🏟️", font=('Arial', 40), bg='#2c3e50', fg='white')
            logo_label.pack(side='left', padx=(0, 10))
        
        # Titre principal
        titre = tk.Label(header_frame, text="SYSTÈME DE GESTION DE FOULE", 
                        font=('Arial', 24, 'bold'), fg='white', bg='#2c3e50')
        titre.pack(side='left', pady=10)
        
        # Frame principal avec poids pour être responsive
        main_frame = tk.Frame(self.root, bg='#2c3e50')
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        main_frame.columnconfigure(0, weight=3)  # Left frame gets more space
        main_frame.columnconfigure(1, weight=1)  # Right frame gets less space
        main_frame.rowconfigure(0, weight=1)
        
        # Frame de gauche - Vidéo et contrôles
        left_frame = tk.Frame(main_frame, bg='#34495e', relief='raised', bd=2)
        left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)  # Video area expands
        
        # Zone d'affichage vidéo
        self.video_label = tk.Label(left_frame, text="📹 Sélectionnez une source vidéo", 
                                   font=('Arial', 16), bg='#34495e', fg='white')
        self.video_label.grid(row=0, column=0, pady=20, sticky='ew')
        
        # Contrôles vidéo
        controles_frame = tk.Frame(left_frame, bg='#34495e')
        controles_frame.grid(row=1, column=0, pady=10, sticky='ew')
        
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
        
        # Frame de droite - Dashboard et alertes avec scroll
        right_frame = tk.Frame(main_frame, bg='#34495e', relief='raised', bd=2)
        right_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        
        # Canvas et scrollbar pour le contenu de droite
        canvas = tk.Canvas(right_frame, bg='#34495e', highlightthickness=0)
        scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#34495e')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        right_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)
        
        # Dashboard
        dashboard_label = tk.Label(scrollable_frame, text="📊 TABLEAU DE BORD", 
                                  font=('Arial', 16, 'bold'), fg='white', bg='#34495e')
        dashboard_label.pack(pady=(10, 10))
        
        # Compteur de personnes
        self.compteur_frame = tk.Frame(scrollable_frame, bg='#2ecc71', relief='raised', bd=3)
        self.compteur_frame.pack(pady=5, padx=20, fill='x')
        
        tk.Label(self.compteur_frame, text="👥 NOMBRE DE PERSONNES", 
                font=('Arial', 12, 'bold'), bg='#2ecc71', fg='white').pack(pady=5)
        
        self.label_nombre = tk.Label(self.compteur_frame, text="0", 
                                    font=('Arial', 36, 'bold'), bg='#2ecc71', fg='white')
        self.label_nombre.pack(pady=10)
        
        # État de sécurité
        self.etat_frame = tk.Frame(scrollable_frame, bg='#2ecc71', relief='raised', bd=3)
        self.etat_frame.pack(pady=5, padx=20, fill='x')
        
        tk.Label(self.etat_frame, text="🛡️ ÉTAT DE SÉCURITÉ", 
                font=('Arial', 12, 'bold'), bg='#2ecc71', fg='white').pack(pady=5)
        
        self.label_etat = tk.Label(self.etat_frame, text="  SÉCURISÉ", 
                                  font=('Arial', 16, 'bold'), bg='#2ecc71', fg='white')
        self.label_etat.pack(pady=10)
        
        # Alertes
        alertes_label = tk.Label(scrollable_frame, text="  SYSTÈME D'ALERTES", 
                                font=('Arial', 16, 'bold'), fg='white', bg='#34495e')
        alertes_label.pack(pady=(20, 10))
        
        # Alerte foule
        self.alerte_foule_frame = tk.Frame(scrollable_frame, bg='#f39c12', relief='raised', bd=3)
        self.alerte_foule_frame.pack(pady=5, padx=20, fill='x')
        
        self.label_alerte_foule = tk.Label(self.alerte_foule_frame, text="  GESTION DE FOULE\nNORMALE", 
                                          font=('Arial', 12, 'bold'), bg='#f39c12', fg='white')
        self.label_alerte_foule.pack(pady=15)
        
        # Alerte arme
        self.alerte_arme_frame = tk.Frame(scrollable_frame, bg='#95a5a6', relief='raised', bd=3)
        self.alerte_arme_frame.pack(pady=5, padx=20, fill='x')
        
        self.label_alerte_arme = tk.Label(self.alerte_arme_frame, text="  DÉTECTION D'ARMES\nINACTIVE", 
                                         font=('Arial', 12, 'bold'), bg='#95a5a6', fg='white')
        self.label_alerte_arme.pack(pady=15)
        
        # Paramètres
        params_label = tk.Label(scrollable_frame, text="  PARAMÈTRES", 
                               font=('Arial', 14, 'bold'), fg='white', bg='#34495e')
        params_label.pack(pady=(20, 10))
        
        # Seuil de foule
        seuil_frame = tk.Frame(scrollable_frame, bg='#34495e')
        seuil_frame.pack(pady=5, padx=20, fill='x')
        
        tk.Label(seuil_frame, text="Seuil foule dangereuse:", 
                font=('Arial', 10), fg='white', bg='#34495e').pack(anchor='w')
        
        self.seuil_var = tk.StringVar(value=str(self.seuil_foule_danger))
        seuil_entry = tk.Entry(seuil_frame, textvariable=self.seuil_var, width=10)
        seuil_entry.pack(anchor='w', pady=2)
        seuil_entry.bind('<Return>', self.mettre_a_jour_seuil)
        
        # Temps de surveillance
        temps_frame = tk.Frame(scrollable_frame, bg='#34495e')
        temps_frame.pack(pady=5, padx=20, fill='x')
        
        tk.Label(temps_frame, text="Temps surveillance (s):", 
                font=('Arial', 10), fg='white', bg='#34495e').pack(anchor='w')
        
        self.temps_var = tk.StringVar(value=str(self.temps_surveillance))
        temps_entry = tk.Entry(temps_frame, textvariable=self.temps_var, width=10)
        temps_entry.pack(anchor='w', pady=2)
        temps_entry.bind('<Return>', self.mettre_a_jour_temps)
        
        # Historique
        self.historique_text = tk.Text(scrollable_frame, height=8, width=40, bg='#2c3e50', fg='white')
        self.historique_text.pack(pady=10, padx=20, fill='x')
        
        # Add listbox and buttons for worker marking
        self.ids_label = tk.Label(self.root, text="Personnes détectées (IDs):", font=('Arial', 10), bg='#2c3e50', fg='white')
        self.ids_label.pack(side='right', anchor='ne', padx=10, pady=(0, 0))
        self.ids_listbox = tk.Listbox(self.root, selectmode=tk.SINGLE, width=20, height=8)
        self.ids_listbox.pack(side='right', anchor='ne', padx=10, pady=(0, 0))
        self.btn_mark_worker = tk.Button(self.root, text="Marquer comme agent", command=self.marquer_worker, bg='#f1c40f', fg='black')
        self.btn_mark_worker.pack(side='right', anchor='ne', padx=10, pady=(0, 0))
        self.btn_unmark_worker = tk.Button(self.root, text="Retirer agent", command=self.demarquer_worker, bg='#e67e22', fg='white')
        self.btn_unmark_worker.pack(side='right', anchor='ne', padx=10, pady=(0, 10))
        
        # Bind mouse wheel to canvas for scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Configure minimum window size
        self.root.update_idletasks()
        self.root.minsize(1200, 700)
        
    def charger_modeles(self):
        """Charge les modèles YOLO"""
        try:
            # Modèle pour détection de personnes (YOLO standard)
            self.model_yolo = YOLO('yolov8n.pt')  # Modèle léger pour personnes
            self.ajouter_log("  Modèle YOLO chargé avec succès")
            
            # Pour la détection d'armes, vous devrez entraîner un modèle spécialisé
            # ou utiliser un modèle pré-entraîné pour objets dangereux
            try:
                self.model_weapons = YOLO('yolov8n.pt')  # Remplacer par modèle d'armes
                self.ajouter_log("  Modèle détection d'armes chargé")
            except:
                self.ajouter_log("  Modèle détection d'armes non disponible")
                
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du chargement des modèles: {str(e)}")
            self.ajouter_log(f"  Erreur chargement modèles: {str(e)}")
    
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
        frame_resultat = frame.copy()
        try:
            resultats = self.model_yolo(frame, conf=0.3)
            personnes_detectees = 0
            armes_detectees = False
            types_armes_detectees = []
            person_boxes = []
            dangerous_boxes = []
            dangerous_labels = []
            for resultat in resultats:
                boxes = resultat.boxes
                if boxes is not None:
                    for box in boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        conf = float(box.conf[0])
                        cls = int(box.cls[0])
                        noms_classes = self.model_yolo.names
                        nom_classe = noms_classes[cls]
                        # Détecter les personnes
                        if nom_classe == 'person' and conf > 0.4:
                            roi = frame[y1:y2, x1:x2]
                            if roi.shape[0] > 0 and roi.shape[1] > 0 and self.is_black(roi):
                                color = (0, 255, 255)
                                cv2.rectangle(frame_resultat, (x1, y1), (x2, y2), color, 2)
                                cv2.putText(frame_resultat, 'AGENT', (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                                continue
                            personnes_detectees += 1
                            person_boxes.append((x1, y1, x2, y2))
                            cv2.rectangle(frame_resultat, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(frame_resultat, f'Personne {conf:.2f}', (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                        # Liste étendue d'objets dangereux/suspects
                        objets_dangereux = {
                            'knife': 'COUTEAU',
                            'scissors': 'CISEAUX',
                            'baseball bat': 'BATTE',
                            'bottle': 'BOUTEILLE',
                            'wine glass': 'VERRE',
                            'cup': 'GOBELET',
                            'hammer': 'MARTEAU',
                            'screwdriver': 'TOURNEVIS',
                            'tie': 'CRAVATE/CORDE',
                            'rope': 'CORDE',
                            'chain': 'CHAÎNE',
                            'umbrella': 'PARAPLUIE',
                            'handbag': 'SAC_SUSPECT',
                            'backpack': 'SAC_A_DOS',
                            'suitcase': 'VALISE',
                            'spoon': 'CUILLÈRE',
                            'fork': 'FOURCHETTE',
                            'bowl': 'BOL_MÉTALLIQUE'
                        }
                        if nom_classe in objets_dangereux:
                            seuil_conf = 0.25
                            if nom_classe in ['chain', 'scissors', 'baseball bat']:
                                seuil_conf = 0.3
                            elif nom_classe in ['chain', 'wine glass', 'cup']:
                                seuil_conf = 0.4
                            if conf > seuil_conf:
                                armes_detectees = True
                                nom_francais = objets_dangereux[nom_classe]
                                types_armes_detectees.append(nom_francais)
                                dangerous_boxes.append((x1, y1, x2, y2))
                                dangerous_labels.append(nom_francais)
                                if nom_classe in ['knife', 'scissors', 'baseball bat']:
                                    couleur = (0, 0, 255)
                                    epaisseur = 4
                                else:
                                    couleur = (0, 100, 255)
                                    epaisseur = 3
                                cv2.rectangle(frame_resultat, (x1, y1), (x2, y2), couleur, epaisseur)
                                cv2.putText(frame_resultat, f'DANGER: {nom_francais}', (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur, 2)
                                cv2.putText(frame_resultat, f'Conf: {conf:.2f}', (x1, y2+20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, couleur, 1)
            # Save screenshot for each dangerous object
            for (dbox, dlabel) in zip(dangerous_boxes, dangerous_labels):
                dx1, dy1, dx2, dy2 = dbox
                save_dir = 'dangerous_persons'
                os.makedirs(save_dir, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                # Save the whole frame with dangerous object highlighted
                frame_copy = frame.copy()
                cv2.rectangle(frame_copy, (dx1, dy1), (dx2, dy2), (0,0,255), 4)
                filename = f"danger_{dlabel}_{timestamp}_frame.jpg"
                cv2.imwrite(os.path.join(save_dir, filename), frame_copy)
            armes_detectees_forme = self.detecter_objets_par_forme(frame, frame_resultat)
            if armes_detectees_forme:
                armes_detectees = True
                types_armes_detectees.extend(armes_detectees_forme)
            self.nombre_personnes = personnes_detectees
            self.historique_personnes.append({
                'temps': datetime.now().strftime("%H:%M:%S"),
                'personnes': self.nombre_personnes,
                'armes': armes_detectees,
                'types_armes': types_armes_detectees
            })
            if len(self.historique_personnes) > 100:
                self.historique_personnes.pop(0)
            cv2.putText(frame_resultat, f'Personnes: {self.nombre_personnes}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            if armes_detectees:
                armes_text = ', '.join(set(types_armes_detectees))
                cv2.putText(frame_resultat, 'ALERTE ARME DETECTEE!', (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                cv2.putText(frame_resultat, f'Types: {armes_text}', (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                self.alerte_arme_active = True
                self.types_armes_courantes = types_armes_detectees
            else:
                self.alerte_arme_active = False
                self.types_armes_courantes = []
        except Exception as e:
            self.ajouter_log(f"  Erreur détection: {str(e)}")
        return frame_resultat

    def detecter_objets_par_forme(self, frame_original, frame_resultat):
        """Détecte des objets dangereux basés sur leur forme (chaînes, cordes, objets longs)"""
        try:
            # Convertir en niveaux de gris
            gray = cv2.cvtColor(frame_original, cv2.COLOR_BGR2GRAY)
            
            # Appliquer un flou pour réduire le bruit
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Détection des contours avec Canny
            edges = cv2.Canny(blurred, 50, 150)
            
            # Trouver les contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            objets_detectes = []
            
            for contour in contours:
                # Calculer l'aire du contour
                area = cv2.contourArea(contour)
                
                # Ignorer les contours trop petits ou trop grands
                if area < 500 or area > 50000:
                    continue
                
                # Calculer le rectangle englobant
                x, y, w, h = cv2.boundingRect(contour)
                
                # Calculer le ratio longueur/largeur
                aspect_ratio = max(w, h) / min(w, h)
                
                # Calculer la longueur du contour
                perimeter = cv2.arcLength(contour, True)
                
                # Détecter objets longs et fins (chaînes, cordes, battes)
                if aspect_ratio > 4 and area > 1000:  # Objet long et fin
                    objets_detectes.append("OBJET_LONG_SUSPECT")
                    cv2.rectangle(frame_resultat, (x, y), (x+w, y+h), (255, 0, 0), 2)
                    cv2.putText(frame_resultat, 'OBJET LONG DÉTECTÉ', 
                               (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                
                # Détecter formes irrégulières qui pourraient être des chaînes
                hull = cv2.convexHull(contour)
                hull_area = cv2.contourArea(hull)
                if hull_area > 0:
                    solidity = area / hull_area
                    
                    # Faible solidité = forme irrégulière comme une chaîne
                    if solidity < 0.3 and area > 2000 and perimeter > 200:
                        objets_detectes.append("CHAÎNE_SUSPECTE")
                        cv2.drawContours(frame_resultat, [contour], -1, (128, 0, 128), 2)
                        cv2.putText(frame_resultat, 'CHAÎNE POSSIBLE', 
                                   (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 0, 128), 2)
            
            return objets_detectes
            
        except Exception as e:
            self.ajouter_log(f"  Erreur détection forme: {str(e)}")
            return []
    
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
            self.ajouter_log(f"  Erreur affichage: {str(e)}")
    
    def verifier_alertes(self):
        self.root.after(0, lambda: self.label_nombre.config(text=str(self.nombre_personnes)))
        # --- Enhanced congestion logic ---
        # Count only non-worker IDs that have been present longer than the threshold
        now = time.time()
        ids_long = [oid for oid, t0 in self.person_entry_times.items() if oid not in self.worker_ids and (now - t0) >= self.temps_surveillance]
        if len(ids_long) >= self.seuil_foule_danger:
            if not self.alerte_foule_active:
                self.compteur_temps_foule = time.time()
                self.alerte_foule_active = True
                self.root.after(0, self.activer_alerte_foule_warning)
            else:
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
            text=f"  FOULE DÉTECTÉE\n{self.nombre_personnes} personnes\nSURVEILLANCE...",
            bg='#f39c12'
        )
        self.compteur_frame.config(bg='#f39c12')
        self.label_nombre.config(bg='#f39c12')
        self.etat_frame.config(bg='#f39c12')
        self.label_etat.config(text="  SURVEILLANCE", bg='#f39c12')
    
    def activer_alerte_foule_danger(self):
        """Active l'alerte foule en mode danger"""
        self.alerte_foule_frame.config(bg='#e74c3c')
        self.label_alerte_foule.config(
            text=f"  ALERTE FOULE!\n{self.nombre_personnes} personnes\nDANGER!",
            bg='#e74c3c'
        )
        self.compteur_frame.config(bg='#e74c3c')
        self.label_nombre.config(bg='#e74c3c')
        self.etat_frame.config(bg='#e74c3c')
        self.label_etat.config(text="  DANGER", bg='#e74c3c')
        
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
        
        self.ajouter_log(f"  ALERTE FOULE ACTIVÉE - {self.nombre_personnes} personnes détectées")
    
    def desactiver_alerte_foule(self):
        """Désactive l'alerte foule"""
        self.alerte_foule_frame.config(bg='#2ecc71')
        self.label_alerte_foule.config(
            text="  GESTION DE FOULE\nNORMALE",
            bg='#2ecc71'
        )
        self.compteur_frame.config(bg='#2ecc71')
        self.label_nombre.config(bg='#2ecc71')
        self.etat_frame.config(bg='#2ecc71')
        self.label_etat.config(text="  SÉCURISÉ", bg='#2ecc71')
        
        self.ajouter_log("  Alerte foule désactivée - Situation normale")
    
    def activer_alerte_arme(self):
        """Active l'alerte arme"""
        self.alerte_arme_frame.config(bg='#e74c3c')
        
        # Afficher les types d'armes détectées
        if self.types_armes_courantes:
            armes_text = ', '.join(set(self.types_armes_courantes))
            self.label_alerte_arme.config(
                text=f"  ARME DÉTECTÉE!\n{armes_text}\nURGENCE!",
                bg='#e74c3c'
            )
        else:
            self.label_alerte_arme.config(
                text="  ARME DÉTECTÉE!\nURGENCE!",
                bg='#e74c3c'
            )
        
        if not hasattr(self, 'derniere_alerte_arme') or time.time() - self.derniere_alerte_arme > 3:
            armes_detectees_str = ', '.join(set(self.types_armes_courantes)) if self.types_armes_courantes else "OBJET DANGEREUX"
            self.ajouter_log(f"  URGENCE - ARME DÉTECTÉE: {armes_detectees_str}")
            self.derniere_alerte_arme = time.time()
            
            # Alarme sonore d'urgence renforcée
            try:
                for i in range(5):  # 5 bips d'alarme
                    duration = 0.2
                    freq = 1200 + (i * 100)  # Fréquence variable
                    sample_rate = 22050
                    frames = int(duration * sample_rate)
                    arr = np.zeros(frames)
                    for j in range(frames):
                        arr[j] = np.sin(2 * np.pi * freq * j / sample_rate)
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
            text="  DÉTECTION D'ARMES\nNORMALE",
            bg='#95a5a6'
        )
    
    def mettre_a_jour_seuil(self, event=None):
        """Met à jour le seuil de foule dangereuse"""
        try:
            nouveau_seuil = int(self.seuil_var.get())
            self.seuil_foule_danger = nouveau_seuil
            self.ajouter_log(f"  Seuil foule mis à jour: {nouveau_seuil}")
        except ValueError:
            messagebox.showerror("Erreur", "Seuil invalide")
    
    def mettre_a_jour_temps(self, event=None):
        """Met à jour le temps de surveillance"""
        try:
            nouveau_temps = int(self.temps_var.get())
            self.temps_surveillance = nouveau_temps
            self.ajouter_log(f"  Temps surveillance mis à jour: {nouveau_temps}s")
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

    def marquer_worker(self):
        selection = self.ids_listbox.curselection()
        if selection:
            id_str = self.ids_listbox.get(selection[0])
            try:
                id_int = int(id_str)
                self.worker_ids.add(id_int)
                self.ajouter_log(f"ID {id_int} marqué comme agent/staff.")
            except:
                pass

    def demarquer_worker(self):
        selection = self.ids_listbox.curselection()
        if selection:
            id_str = self.ids_listbox.get(selection[0])
            try:
                id_int = int(id_str)
                if id_int in self.worker_ids:
                    self.worker_ids.remove(id_int)
                    self.ajouter_log(f"ID {id_int} retiré de la liste des agents.")
            except:
                pass

    def update_ids_listbox(self):
        self.ids_listbox.delete(0, tk.END)
        for oid in sorted(self.current_ids):
            suffix = " (agent)" if oid in self.worker_ids else ""
            self.ids_listbox.insert(tk.END, f"{oid}{suffix}")

    def is_black(self, roi):
        # Convert ROI to HSV and check for black dominance
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # Define black range (low value, any hue and saturation)
        lower_black = np.array([0, 0, 0])
        upper_black = np.array([180, 255, 50])
        mask = cv2.inRange(hsv, lower_black, upper_black)
        black_ratio = cv2.countNonZero(mask) / (roi.shape[0] * roi.shape[1])
        return black_ratio > 0.15  # 15% of the box is black

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