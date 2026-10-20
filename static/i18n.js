/* ADN Creations bilingual support. French is the default (Quebec Charter of
   the French Language); English is one tap away. Static pages carry French
   copy inline with data-i18n keys; this file swaps in English on demand and
   restores French when toggling back. Language persists in localStorage and
   the adn_lang cookie (the cookie is what server-rendered pages read). */
(function () {
  "use strict";

  var I18N = {
    fr: {
      "nav.work": "Réalisations", "nav.shop": "Boutique", "nav.engraving": "Gravure",
      "nav.portraits": "Portraits", "nav.progress": "En cours", "nav.about": "À propos",
      "nav.contact": "Contact", "nav.reviews": "Avis", "nav.cta": "Magasiner", "menu": "Menu",
      "nav.suggest": "Idées",
      "follow.ms": "Suivez nos créations sur Making Stuff",
      "footer.tag": "Entreprise de design en ingénierie. Fabrication additive faite à la main à Montréal, avec des matériaux d'origine végétale.",
      "footer.explore": "Explorer", "footer.contact": "Contact",
      "footer.rights": "Tous droits réservés.", "footer.made": "Conçu et fabriqué à Montréal.",
      "footer.privacy": "Confidentialité", "footer.terms": "Conditions d'utilisation",
      "footer.office": "Bureau du centre-ville : 204, rue du Saint-Sacrement, bureau 300, H2Y 1W8 Montréal (QC)",

      "home.kicker": "Entreprise de design en ingénierie, Montréal",
      "home.h1": "Conçu ici. Fait à la main ici.",
      "home.oratory": "En vente à la boutique de l'Oratoire Saint-Joseph",
      "home.lede": "ADN Creations est une entreprise de design en ingénierie à Montréal. Art dévotionnel, objets de précision et fabrication sur mesure, conçus et imprimés en 3D avec des matériaux d'origine végétale.",
      "home.shop_btn": "Voir la boutique", "home.work_btn": "Voir les réalisations",
      "home.feat_h": "Réalisations en vedette",
      "home.feat1_t": "Buste de saint Frère André, édition collectionneur",
      "home.feat1_d": "Un buste de 39 cm sur un socle en bois teinté foncé avec une plaque de laiton. Pièce unique, finie à la main.",
      "home.feat2_t": "Lampes de prière à 4 faces",
      "home.feat2_d": "Des faces lithophanes qui s'illuminent de l'intérieur, conçues, imprimées et assemblées à Montréal.",
      "home.feat3_t": "Gravure au laser",
      "home.feat3_d": "Gravure au laser personnalisée sur briquets, tasses de voyage et bois, avec nos lasers à fibre et à diode xTool.",
      "home.dept_h": "Magasiner par rayon",
      "home.dept_rel_t": "Religieux", "home.dept_rel_d": "Lampes dévotionnelles, bustes et art sacré.",
      "home.dept_ele_t": "Électronique", "home.dept_ele_d": "Lampes et objets imprimés avec lumière et mouvement.",
      "home.dept_gag_t": "Humour", "home.dept_gag_d": "Articles de fantaisie et humoristiques.",
      "home.build_h": "En chantier à l'atelier",
      "home.build_p": "Des projets en cours et des prototypes qui prennent forme.",
      "home.build_btn": "Suivre le chantier",
      "home.reviews_h": "Ce que nos clients disent",
      "home.reviews_all": "Voir tous les avis",
      "home.reviews_loading": "Chargement des avis...",
      "home.cta_h": "Suivez nos créations sur Making Stuff",
      "home.cta_p": "Nouveautés, expériences et vie d'atelier à Montréal, directement dans votre fil.",
      "home.cta_eng": "Gravure personnalisée ?",
      "home.cta_eng_link": "Nous faisons aussi ça.",

      "work.kicker": "Portfolio", "work.h1": "Réalisations choisies",
      "work.lede": "Une sélection de pièces conçues et fabriquées à Montréal.",
      "work.c1_t": "Buste de saint Frère André, édition collectionneur",
      "work.c1_d": "Un buste de 39 cm sur un socle en bois teinté foncé avec une plaque de laiton. Fabrication additive grand format en matériaux d'origine végétale, fini à la main. Pièce unique.",
      "work.c2_t": "Lampes de prière à 4 faces",
      "work.c2_d": "Des faces lithophanes qui s'illuminent de l'intérieur. Éditions Carlo Acutis et Fulton Sheen, conçues, imprimées et assemblées à Montréal.",
      "work.c3_t": "Lampes commémoratives personnalisées",
      "work.c3_d": "Des lampes à quatre faces à partir de vos photos ou de nos illustrations de saints. En vente à la boutique de l'Oratoire Saint-Joseph.",
      "work.c4_t": "Lampes scène de la Nativité",
      "work.c4_d": "La Nativité en lampe lithophane lumineuse. Un succès constant à la boutique de l'Oratoire.",
      "work.c5_t": "Gravure au laser",
      "work.c5_d": "Gravure au laser personnalisée sur briquets, tasses de voyage et bois, avec nos lasers à fibre et à diode xTool.",
      "work.c6_t": "Étuis pour cartes à jouer italiennes",
      "work.c6_d": "Des étuis ajustés pour les jeux Scopa et Briscola, imprimés avec des tolérances précises.",
      "work.c7_badge": "En développement",
      "work.c7_t": "Horloge mécanique à régulateur",
      "work.c7_d": "Échappement à chevilles, rouage de 135:1, boîtier imprimé.",
      "work.c7_link": "Suivez le projet sur la page En cours.",
      "photo.soon": "Photo à venir",

      "shop.kicker": "Boutique", "shop.h1": "La collection",
      "shop.lede": "Chaque pièce est conçue et faite à la main à Montréal. Expédition à taux fixe partout au Canada et aux États-Unis.",
      "shop.tab_all": "Tout", "shop.tab_rel": "Religieux",
      "shop.tab_ele": "Électronique", "shop.tab_gag": "Humour",
      "shop.build_h": "En chantier à l'atelier",
      "shop.build_p": "Des projets en cours qui deviendront des produits. Suivez leur progression.",
      "shop.build_btn": "Suivre le chantier",
      "shop.soon_h": "Bientôt disponible",
      "shop.custom_h": "Sur mesure",
      "shop.custom_p": "Chaque projet sur mesure passe par la même porte : choisissez votre point de départ.",
      "shop.cust1_t": "Lampe commémorative sur mesure",
      "shop.cust1_d": "Vos photos deviennent une lampe à 4 faces. Composez la vôtre dans l'atelier en ligne.",
      "shop.cust2_t": "Gravure personnalisée",
      "shop.cust2_d": "Briquets, tasses, bois et vos propres objets, gravés au laser.",
      "shop.cust3_t": "Un projet en tête ?",
      "shop.cust3_d": "Une pièce à concevoir ou à imprimer ? Décrivez-la, on vous revient avec un plan et un prix.",
      "shop.cust_btn": "Commencer",
      "shop.search_ph": "Rechercher un produit...",
      "shop.sec_religious": "Articles religieux",
      "shop.sec_italian": "Produits italiens",
      "shop.sec_gag": "Cadeaux humoristiques",
      "shop.sec_more": "Gravure et objets pratiques",
      "shop.no_results": "Aucun produit ne correspond à votre recherche.",
      "js.loading": "Chargement de la collection...",
      "js.empty": "Rien dans ce rayon pour le moment. Revenez bientôt.",
      "js.load_err": "Désolé, la boutique n'a pas pu être chargée. Veuillez actualiser la page et réessayer.",
      "js.view": "Voir", "js.design": "Créez le vôtre",
      "js.preorder": "Précommande", "js.only_left": "Plus que {n} en stock",
      "js.coming_soon": "Bientôt disponible", "js.in_works": "En préparation",

      "engr.kicker": "Gravure personnalisée", "engr.h1": "Vos mots, gravés pour durer.",
      "engr.lede": "Nous gravons votre texte ou votre dessin sur des briquets, des tasses de voyage et du bois avec nos lasers à fibre et à diode xTool.",
      "engr.how_h": "Comment ça marche",
      "engr.s1_t": "Choisissez un produit",
      "engr.s1_d": "Choisissez un produit ci-dessus, ou décrivez votre propre objet dans le formulaire.",
      "engr.s2_t": "Envoyez votre texte ou votre dessin",
      "engr.s2_d": "Utilisez le formulaire ci-dessous pour nous dire ce que vous voulez graver.",
      "engr.s3_t": "Nous gravons et nous expédions",
      "engr.s3_d": "Lasers à fibre et à diode xTool, puis expédition à taux fixe.",
      "engr.form_h": "Un projet de gravure sur mesure ?",
      "engr.name": "Nom", "engr.email": "Courriel", "engr.product": "Produit",
      "engr.opt1": "Briquet gravé", "engr.opt2": "Tasse de voyage Contigo gravée",
      "engr.opt3": "Mon propre objet", "engr.opt4": "Autre chose",
      "engr.msg_label": "Que devons-nous graver ?",
      "engr.send": "Envoyer la demande",
      "engr.pick_h": "Choisissez ce que nous gravons",
      "engr.pick_sub": "Commandez en ligne, la gravure est comprise. Pour le bois, une bouteille ou votre propre objet, passez par le formulaire plus bas.",
      "engr.badge": "Le plus populaire",
      "engr.light_t": "Briquet gravé sur mesure",
      "engr.light_d": "Briquet style Zippo dans son boîtier cadeau. Choisissez un de nos 12 dessins ou envoyez le vôtre, gravé au laser à fibre.",
      "engr.light_p": "24,99 $",
      "engr.mug_t": "Tasse de voyage gravée",
      "engr.mug_d": "Tasse Contigo isolée avec votre texte ou votre logo gravé au laser. Un cadeau qui se remarque.",
      "engr.mug_p": "33,99 $",
      "engr.cust_t": "Gravure sur mesure",
      "engr.cust_d": "Bois, planches à découper, bouteilles, ou votre propre objet. Décrivez votre projet, on s'occupe du reste.",
      "engr.order_btn": "Commander",
      "engr.ask_btn": "Décrire mon projet",
      "engr.ok": "Demande reçue. Nous répondons en un jour ou deux.",
      "engr.err2": "Quelque chose n'a pas fonctionné. Veuillez réessayer.",
      "engr.err3": "Impossible d'envoyer votre demande. Veuillez réessayer.",

      "por.kicker": "Portraits", "por.h1": "Vos portraits, imprimés en UV.",
      "por.lede": "Notre imprimante UV arrive bientôt à l'atelier. Des portraits aux couleurs vives, imprimés directement sur une foule de supports.",
      "por.soon_badge": "En préparation",
      "por.soon_h": "L'imprimante UV est en route",
      "por.soon_p": "Les portraits personnalisés s'en viennent très bientôt. Dites-nous déjà ce que vous aimeriez voir.",
      "por.form_h": "Proposez votre idée",
      "por.form_p": "Dites-nous ce que vous aimeriez en portrait. Les meilleures idées deviennent des produits.",
      "por.name": "Nom", "por.email": "Courriel",
      "por.idea_label": "Votre idée",
      "por.idea_ph": "p. ex. un portrait de mon grand-père sur bois...",
      "por.send": "Envoyer mon idée",
      "por.ok": "Idée reçue. Merci, nous vous répondrons bientôt.",
      "por.err2": "Quelque chose n'a pas fonctionné. Veuillez réessayer.",
      "por.err3": "Impossible d'envoyer votre idée. Veuillez réessayer.",

      "prog.kicker": "En cours", "prog.h1": "À l'atelier",
      "prog.lede": "Ce qui est sur l'établi en ce moment, et ce que nous avons livré.",
      "prog.wip_h": "Projets en cours", "prog.ann_h": "Annonces",
      "prog.loading": "Chargement...", "prog.empty": "Rien ici pour le moment.",
      "prog.noupd": "Aucune mise à jour pour le moment.",
      "prog.inprog": "En cours",

      "about.kicker": "À propos", "about.h1": "Un ingénieur, un atelier.",
      "about.lede": "Je suis Antonio Daniele, étudiant en génie mécanique à McGill et fondateur d'ADN Creations. J'ai construit ma première imprimante 3D à dix ans et je conçois et fabrique des objets depuis onze ans.",
      "about.p1": "Tout est conçu à l'interne à Montréal et imprimé avec des matériaux d'origine végétale. La fabrication additive réduit les déchets au minimum, et chaque pièce naît d'une page blanche dans mes propres fichiers de conception. L'atelier est à LaSalle.",
      "about.p2": "Mes pièces dévotionnelles sont en vente à la boutique de l'Oratoire Saint-Joseph à Montréal.",
      "about.p3": "L'objectif est de faire d'ADN Creations une entreprise de design en ingénierie : de nouveaux produits, de nouveaux rayons, et une fabrication qui reste locale.",
      "about.s1_n": "11", "about.s1_l": "Années d'impression 3D",
      "about.s2_n": "1", "about.s2_l": "Atelier à Montréal",
      "about.s3_n": "PLA", "about.s3_l": "Matériaux d'origine végétale",
      "about.photo_alt": "Buste de saint Frère André en finition à l'atelier",
      "about.photo_cap": "Buste de saint Frère André, 32 cm, en finition à l'atelier de LaSalle.",
      "about.work_btn": "Voir les réalisations", "about.shop_btn": "Voir la boutique",
      "about.faq_h": "Questions fréquentes",
      "about.faq1_q": "Que fabrique ADN Creations ?",
      "about.faq1_a": "Des articles dévotionnels catholiques (lampes de prière à quatre faces, lampes scène de la Nativité, bustes de saints), des lampes commémoratives sur mesure et des objets gravés au laser comme des briquets et des bouteilles. Tout est conçu et fini à Montréal.",
      "about.faq2_q": "Qu'est-ce qu'une lampe de prière à quatre faces ?",
      "about.faq2_a": "Une lampe de 10x7x7 cm avec quatre panneaux en lithophane lumineux et une DEL chaude à piles. L'édition Carlo Acutis montre la Vierge Marie, le portrait de Carlo, Carlo avec l'Eucharistie et son sanctuaire d'Assise. 24,99 $ CA.",
      "about.faq3_q": "Qu'est-ce que la lampe scène de la Nativité ?",
      "about.faq3_a": "Une Sainte Famille de 10 cm sous le dôme de l'Oratoire Saint-Joseph, imprimée en paroi fine pour diffuser la lumière comme un lithophane, avec pile incluse. 29,99 $ CA, aussi en vente à la boutique de l'Oratoire.",
      "about.faq4_q": "Où puis-je acheter ?",
      "about.faq4_a": "En ligne à adncreations.ca (expédition à taux fixe : 5 $ CA au Canada, 10 $ CA aux États-Unis, 15 $ CA à l'international, livraison en 1 à 2 semaines, retours de 14 jours) et à la boutique de l'Oratoire Saint-Joseph à Montréal.",
      "about.faq5_q": "Les produits sont-ils faits à la main ?",
      "about.faq5_a": "Oui. Chaque pièce est conçue à partir de zéro et imprimée en 3D à l'atelier de LaSalle en bioplastique d'origine végétale, puis finie à la main.",
      "about.faq6_q": "Qui est derrière ADN Creations ?",
      "about.faq6_a": "Antonio Daniele, étudiant en génie mécanique à McGill avec onze ans d'expérience en impression 3D. Il a construit sa première imprimante 3D quand il était enfant.",

      "contact.kicker": "Contact", "contact.h1": "Parlez à l'atelier.",
      "contact.p": "Pour le travail sur mesure, la vente en gros et la presse, le courriel est le plus rapide.",
      "contact.office_h": "Bureau du centre-ville",
      "contact.addr1": "204, rue du Saint-Sacrement, bureau 300",
      "contact.addr2": "H2Y 1W8 Montréal (QC)",
      "contact.response": "Nous répondons en général en 24 heures ouvrables.",
      "contact.workshop": "Atelier de fabrication : LaSalle, Montréal.",

      "thanks.loading": "Chargement de votre commande...",
      "thanks.notfound": "Nous n'avons pas trouvé cette commande. Vérifiez votre lien de confirmation.",
      "thanks.notfound2": "Nous n'avons pas trouvé cette commande. Si vous venez de payer, attendez un moment et actualisez.",
      "thanks.confirmed": "Commande confirmée", "thanks.h1": "Merci.",
      "thanks.preorder": "Ceci est une précommande. Expédition prévue : {date}.",
      "thanks.q": "Des questions sur votre commande ? Écrivez à",

      "lamp.kicker": "Personnalisé", "lamp.h1": "Créez votre lampe commémorative",
      "lamp.lede": "Choisissez l'une des quatre faces ci-dessous, puis une illustration de saint ou téléversez votre propre photo pour chaque face. Chaque lampe est conçue et faite à la main à Montréal avec des matériaux d'origine végétale, avec une chaude lumière vacillante.",
      "lamp.cancel": "Votre paiement a été annulé. Votre création est toujours ci-dessous.",
      "lamp.s1": "Étape 1 : choisissez vos quatre faces",
      "lamp.progress": "{n} faces sur 4 choisies.",
      "lamp.notchosen": "Pas encore choisie",
      "lamp.nothing": "Rien de choisi pour le moment",
      "lamp.change": "Changer la face {n}", "lamp.choose": "Choisir la face {n}",
      "lamp.side": "Face {n}", "lamp.picker_t": "Choisir la face {n}",
      "lamp.picker_p": "Touchez une illustration, ou téléversez votre propre photo pour cette face.",
      "lamp.upload_l": "Ou téléversez votre propre photo",
      "lamp.upload_p": "Votre photo n'est conservée que pour fabriquer votre lampe.",
      "lamp.back": "Retour à mes faces",
      "lamp.uploading": "Téléversement de votre photo...",
      "lamp.upload_err": "Désolé, cette photo n'a pas pu être téléversée. Essayez une autre image.",
      "lamp.s2": "Étape 2 : choisissez votre paquet",
      "lamp.single": "Une seule 39,99 $", "lamp.pack4": "Paquet de 4 99,99 $",
      "lamp.pack_note": "Le paquet de 4 comprend 4 lampes du même modèle.",
      "lamp.extra_note": "Des exemplaires supplémentaires du même modèle sont à 24,99 $ chacun.",
      "lamp.s3": "Étape 3 : paiement",
      "lamp.checkout": "Passer à la caisse",
      "lamp.secure": "Paiement sécurisé avec Stripe. Expédition : 5 $ Canada, 10 $ États-Unis, 15 $ international. Livraison : 1 à 2 semaines. L'adresse de livraison est demandée au paiement.",
      "lamp.ship_country": "Pays de livraison",
      "lamp.ship_ca": "Canada — 5 $",
      "lamp.ship_us": "États-Unis — 10 $",
      "lamp.ship_intl": "International — 15 $",
      "lamp.gallery_err": "Désolé, la galerie d'illustrations n'a pas pu être chargée. Veuillez actualiser la page.",
      "lamp.need_sides": "Veuillez choisir une illustration ou une photo pour la face {list} avant de passer à la caisse.",
      "lamp.preparing": "Préparation de votre paiement...",
      "lamp.start_err": "Désolé, le paiement n'a pas pu démarrer. Veuillez réessayer.",
      "lamp.yourphoto": "Votre photo",

      "priv.kicker": "Confidentialité", "priv.h1": "Vie privée",
      "priv.p1": "ADN Creations ne recueille que ce qui est nécessaire pour faire fonctionner la boutique : les détails de votre commande, votre adresse d'expédition et ce que vous envoyez par les formulaires de demande. Les informations de paiement sont traitées en toute sécurité par Stripe et ne touchent jamais nos serveurs.",
      "priv.p2": "Nous comptons les visites de façon anonyme, par jour et par page seulement. Pas de comptes, pas de témoins de suivi, pas de profils publicitaires.",
      "priv.p3": "Vos informations ne sont jamais vendues ni partagées avec des tiers, sauf ce qui est nécessaire pour livrer votre commande, comme transmettre votre adresse à un transporteur.",
      "priv.p4": "Des questions sur vos données :",

      "terms.kicker": "Conditions", "terms.h1": "Conditions de vente",
      "terms.p1": "Tous les produits sont conçus et faits à la main par ADN Creations à Montréal, Québec. Les prix sont en dollars canadiens.",
      "terms.p2": "Chaque pièce est fabriquée sur commande ou finie à la main, alors de petites variations font partie du travail. Si votre commande arrive endommagée ou incorrecte, contactez-nous dans les 14 jours et nous corrigerons la situation.",
      "terms.p3": "Les précommandes sont facturées à la caisse. La date d'expédition prévue indiquée sur la page du produit est notre meilleure estimation; nous vous écrirons par courriel si elle change.",
      "terms.p4": "Les articles gravés sur mesure sont vente finale, sauf s'ils arrivent endommagés ou ne correspondent pas au texte approuvé.",
      "terms.p7": "Retours : si une pièce standard ne vous convient pas, contactez-nous dans les 14 jours suivant la réception pour un retour ou un échange. L'article doit être inutilisé et dans son emballage d'origine; les frais de retour sont à votre charge, sauf si l'erreur vient de nous.",
      "terms.p5": "L'expédition est à taux fixe : 5 $ au Canada, 10 $ aux États-Unis, 15 $ à l'international. La livraison prend de 1 à 2 semaines.",
      "terms.p6": "Contact :",

      "sg.kicker": "Vos idées", "sg.h1": "Suggérez un projet.",
      "sg.lede": "Vous avez une idée de produit, un projet sur mesure ou une collaboration en tête ? Dites-le-nous. Nous lisons chaque suggestion.",
      "sg.form_h": "Proposer une idée",
      "sg.name": "Nom", "sg.email": "Courriel",
      "sg.title_l": "Titre de l'idée", "sg.title_ph": "p. ex. une lampe veilleuse pour bébé...",
      "sg.desc_l": "Description", "sg.desc_ph": "Décrivez votre idée en quelques phrases.",
      "sg.cat_l": "Catégorie",
      "sg.cat_product": "Idée de produit", "sg.cat_custom": "Travail sur mesure",
      "sg.cat_collab": "Collaboration", "sg.cat_other": "Autre",
      "sg.send": "Envoyer ma suggestion",
      "sg.ok": "Suggestion reçue. Merci, nous vous répondrons si votre idée est retenue.",
      "sg.err2": "Quelque chose n'a pas fonctionné. Veuillez réessayer.",
      "sg.err3": "Impossible d'envoyer votre suggestion. Veuillez réessayer.",

      "login.title": "Connexion vendeur | ADN Creations",
      "login.h": "Connexion vendeur",
      "login.user": "Nom d'utilisateur", "login.pass": "Mot de passe",
      "login.submit": "Se connecter", "login.back": "Retour au site",
      "login.bad": "Nom d'utilisateur ou mot de passe incorrect.",
      "login.disabled": "La connexion par mot de passe n'est pas encore configurée. Utilisez votre lien d'administration."
    },
    en: {
      "nav.work": "Work", "nav.shop": "Shop", "nav.engraving": "Engraving",
      "nav.portraits": "Portraits", "nav.progress": "Progress", "nav.about": "About",
      "nav.contact": "Contact", "nav.reviews": "Reviews", "nav.cta": "Shop now", "menu": "Menu",
      "nav.suggest": "Ideas",
      "follow.ms": "Follow our builds on Making Stuff",
      "footer.tag": "Engineering design company. Hand crafted additive manufacturing in Montreal, from plant-based materials.",
      "footer.explore": "Explore", "footer.contact": "Contact",
      "footer.rights": "All rights reserved.", "footer.made": "Designed and built in Montreal.",
      "footer.privacy": "Privacy", "footer.terms": "Terms of use",
      "footer.office": "Downtown office: 204 rue du Saint-Sacrement, Espace 300, H2Y 1W8 Montréal QC",

      "home.kicker": "Engineering design company, Montreal",
      "home.h1": "Designed here. Hand crafted here.",
      "home.oratory": "Sold at the Saint Joseph's Oratory boutique",
      "home.lede": "ADN Creations is an engineering design company in Montreal. Devotional art, precision objects, and custom manufacturing, designed and 3D printed from plant-based materials.",
      "home.shop_btn": "Shop the collection", "home.work_btn": "See the work",
      "home.feat_h": "Featured work",
      "home.feat1_t": "Saint Frere Andre Collector's Edition Bust",
      "home.feat1_d": "A 39 cm bust on a dark stained wood base with a brass name plate. One of one, finished by hand.",
      "home.feat2_t": "4-Face Prayer Lamps",
      "home.feat2_d": "Lithophane faces that glow from within, designed, printed, and assembled in Montreal.",
      "home.feat3_t": "Laser Engraving",
      "home.feat3_d": "Custom laser engraving on lighters, travel mugs, and wood, with our xTool fiber and diode lasers.",
      "home.dept_h": "Shop by department",
      "home.dept_rel_t": "Religious", "home.dept_rel_d": "Devotional lamps, busts, and sacred art.",
      "home.dept_ele_t": "Electronic", "home.dept_ele_d": "Lamps and printed objects with light and motion.",
      "home.dept_gag_t": "Gag", "home.dept_gag_d": "Novelty and funny items.",
      "home.build_h": "On the bench right now",
      "home.build_p": "Works in progress and prototypes taking shape.",
      "home.build_btn": "Follow the build",
      "home.reviews_h": "What our customers say",
      "home.reviews_all": "See all reviews",
      "home.reviews_loading": "Loading reviews...",
      "home.cta_h": "Follow our builds on Making Stuff",
      "home.cta_p": "New pieces, experiments, and shop life from Montreal, straight to your feed.",
      "home.cta_eng": "Custom engraving?",
      "home.cta_eng_link": "We do that too.",

      "work.kicker": "Portfolio", "work.h1": "Selected work",
      "work.lede": "A selection of pieces designed and built in Montreal.",
      "work.c1_t": "Saint Frere Andre Collector's Edition Bust",
      "work.c1_d": "A 39 cm bust on a dark stained wood base with a brass name plate. Large-format additive manufacturing in plant-based materials, finished by hand. One of one.",
      "work.c2_t": "4-Face Prayer Lamps",
      "work.c2_d": "Lithophane faces that glow from within. Carlo Acutis and Fulton Sheen editions, designed, printed, and assembled in Montreal.",
      "work.c3_t": "Custom Memorial Lamps",
      "work.c3_d": "Four-sided lamps from your photos or our saint illustrations. Carried in the boutique of Saint Joseph's Oratory.",
      "work.c4_t": "Nativity Scene Lamps",
      "work.c4_d": "The Nativity rendered as a glowing lithophane lamp. A steady seller at the Oratory boutique.",
      "work.c5_t": "Laser Engraving",
      "work.c5_d": "Custom laser engraving on lighters, travel mugs, and wood, with xTool fiber and diode lasers.",
      "work.c6_t": "Italian Playing-Card Cases",
      "work.c6_d": "Fitted cases for Scopa and Briscola decks, printed to precise tolerances.",
      "work.c7_badge": "In development",
      "work.c7_t": "Mechanical Regulator Clock",
      "work.c7_d": "Deadbeat escapement, 135:1 going train, printed case.",
      "work.c7_link": "Follow along on the Progress page.",
      "photo.soon": "Photo coming soon",

      "shop.kicker": "Shop", "shop.h1": "The collection",
      "shop.lede": "Every piece is designed and hand crafted in Montreal. Flat-rate shipping across Canada and the US.",
      "shop.tab_all": "All", "shop.tab_rel": "Religious",
      "shop.tab_ele": "Electronic", "shop.tab_gag": "Gag",
      "shop.build_h": "On the bench right now",
      "shop.build_p": "Works in progress on their way to becoming products. Follow along.",
      "shop.build_btn": "Follow the build",
      "shop.soon_h": "Coming soon",
      "shop.custom_h": "Made to order",
      "shop.custom_p": "Every custom project goes through the same door: pick your starting point.",
      "shop.cust1_t": "Custom memorial lamp",
      "shop.cust1_d": "Your photos become a 4-face lamp. Design yours in the online studio.",
      "shop.cust2_t": "Custom engraving",
      "shop.cust2_d": "Lighters, mugs, wood, and your own items, laser engraved.",
      "shop.cust3_t": "Have a project in mind?",
      "shop.cust3_d": "A part to design or print? Describe it, we come back with a plan and a price.",
      "shop.cust_btn": "Start",
      "shop.search_ph": "Search products...",
      "shop.sec_religious": "Religious items",
      "shop.sec_italian": "Italian goods",
      "shop.sec_gag": "Gag gifts",
      "shop.sec_more": "Engraving and everyday items",
      "shop.no_results": "No products match your search.",
      "js.loading": "Loading the collection...",
      "js.empty": "Nothing in this department yet. Check back soon.",
      "js.load_err": "Sorry, the shop could not be loaded. Please refresh the page and try again.",
      "js.view": "View", "js.design": "Design yours",
      "js.preorder": "Preorder", "js.only_left": "Only {n} left",
      "js.coming_soon": "Coming soon", "js.in_works": "In the works",

      "engr.kicker": "Custom engraving", "engr.h1": "Your words, engraved to last.",
      "engr.lede": "We engrave your text or artwork on lighters, travel mugs, and wood with xTool fiber and diode lasers.",
      "engr.how_h": "How it works",
      "engr.s1_t": "Pick a product",
      "engr.s1_d": "Pick a product above, or describe your own item in the form.",
      "engr.s2_t": "Send your text or design",
      "engr.s2_d": "Use the form below to tell us what you want engraved.",
      "engr.s3_t": "We engrave and ship it",
      "engr.s3_d": "xTool fiber and diode lasers, then flat-rate shipping.",
      "engr.form_h": "A custom engraving project?",
      "engr.name": "Name", "engr.email": "Email", "engr.product": "Product",
      "engr.opt1": "Engraved Lighter", "engr.opt2": "Engraved Contigo Travel Mug",
      "engr.opt3": "My own item", "engr.opt4": "Something else",
      "engr.msg_label": "What should we engrave?",
      "engr.send": "Send request",
      "engr.pick_h": "Pick what we engrave",
      "engr.pick_sub": "Order online, engraving is included. For wood, a bottle, or your own item, use the form below.",
      "engr.badge": "Most popular",
      "engr.light_t": "Custom Engraved Lighter",
      "engr.light_d": "Zippo-style lighter in its gift case. Pick one of our 12 designs or upload your own, engraved with the fiber laser.",
      "engr.light_p": "$24.99",
      "engr.mug_t": "Engraved Travel Mug",
      "engr.mug_d": "Insulated Contigo mug with your text or logo laser engraved. A gift people actually keep.",
      "engr.mug_p": "$33.99",
      "engr.cust_t": "Custom engraving",
      "engr.cust_d": "Wood, cutting boards, bottles, or your own item. Describe your project, we handle the rest.",
      "engr.order_btn": "Order",
      "engr.ask_btn": "Describe my project",
      "engr.ok": "Request received. We reply within a day or two.",
      "engr.err2": "Something went wrong. Please try again.",
      "engr.err3": "Could not send your request. Please try again.",

      "por.kicker": "Portraits", "por.h1": "Your portraits, UV printed.",
      "por.lede": "Our UV printer is arriving at the workshop soon. Vivid portraits printed directly on all kinds of surfaces.",
      "por.soon_badge": "In the works",
      "por.soon_h": "The UV printer is on its way",
      "por.soon_p": "Custom portraits are coming very soon. Tell us already what you would like to see.",
      "por.form_h": "Pitch your idea",
      "por.form_p": "Tell us what you would like as a portrait. The best ideas become products.",
      "por.name": "Name", "por.email": "Email",
      "por.idea_label": "Your idea",
      "por.idea_ph": "e.g. a portrait of my grandfather on wood...",
      "por.send": "Send my idea",
      "por.ok": "Idea received. Thank you, we will reply soon.",
      "por.err2": "Something went wrong. Please try again.",
      "por.err3": "Could not send your idea. Please try again.",

      "prog.kicker": "Progress", "prog.h1": "From the workshop",
      "prog.lede": "What is on the bench right now, and what we have shipped.",
      "prog.wip_h": "Work in progress", "prog.ann_h": "Announcements",
      "prog.loading": "Loading...", "prog.empty": "Nothing here yet.",
      "prog.noupd": "No updates yet.",
      "prog.inprog": "In progress",

      "about.kicker": "About", "about.h1": "One engineer, one workshop.",
      "about.lede": "I'm Antonio Daniele, a mechanical engineering student at McGill and the founder of ADN Creations. I built my first 3D printer at ten and I have been designing and making things for eleven years.",
      "about.p1": "Everything is designed in house in Montreal, and printed from plant-based materials. Additive manufacturing keeps waste to a minimum, and every piece starts from a blank page in my own design files. The workshop is in LaSalle.",
      "about.p2": "My devotional pieces are carried in the boutique of Saint Joseph's Oratory in Montreal.",
      "about.p3": "The goal is to grow ADN Creations into an engineering design company: new products, new departments, and manufacturing that stays local.",
      "about.s1_n": "11", "about.s1_l": "Years of 3D printing",
      "about.s2_n": "1", "about.s2_l": "Workshop in Montreal",
      "about.s3_n": "PLA", "about.s3_l": "Plant-based materials",
      "about.photo_alt": "Saint Frère André bust being finished in the workshop",
      "about.photo_cap": "Saint Frère André bust, 32 cm, being finished in the LaSalle workshop.",
      "about.work_btn": "See the work", "about.shop_btn": "Shop the collection",
      "about.faq_h": "Frequently asked questions",
      "about.faq1_q": "What does ADN Creations make?",
      "about.faq1_a": "Devotional Catholic products (4-face prayer lamps, nativity scene lamps, saint busts), custom memorial lamps, and laser-engraved goods such as lighters and bottles. Everything is designed and finished in Montreal.",
      "about.faq2_q": "What is a 4-face prayer lamp?",
      "about.faq2_a": "A 10x7x7 cm lamp with four glowing lithophane panels and a warm battery LED. The Carlo Acutis edition shows the Virgin Mary, Carlo's portrait, Carlo with the Eucharist, and his Assisi sanctuary. CA$24.99.",
      "about.faq3_q": "What is the nativity scene lamp?",
      "about.faq3_a": "A 10 cm Holy Family nativity under the dome of Saint Joseph's Oratory, printed thin so it glows like a lithophane with a battery light inside. CA$29.99, also sold at the Oratory boutique.",
      "about.faq4_q": "Where can I buy?",
      "about.faq4_a": "Online at adncreations.ca (flat-rate shipping: CA$5 Canada, CA$10 USA, CA$15 worldwide, delivery in 1-2 weeks, 14-day returns) and at the Saint Joseph's Oratory boutique in Montreal.",
      "about.faq5_q": "Are the products handmade?",
      "about.faq5_a": "Yes. Every piece is designed from scratch and 3D printed in the LaSalle workshop from plant-based bioplastic, then hand-finished.",
      "about.faq6_q": "Who is behind ADN Creations?",
      "about.faq6_a": "Antonio Daniele, a mechanical engineering student at McGill with 11 years of 3D printing experience. He built his first 3D printer as a kid.",

      "contact.kicker": "Contact", "contact.h1": "Talk to the workshop.",
      "contact.p": "For custom work, wholesale, and press, email is fastest.",
      "contact.office_h": "Downtown office",
      "contact.addr1": "204 rue du Saint-Sacrement, Espace 300",
      "contact.addr2": "H2Y 1W8 Montréal QC",
      "contact.response": "We usually reply within 24 business hours.",
      "contact.workshop": "Production workshop: LaSalle, Montreal.",

      "thanks.loading": "Loading your order...",
      "thanks.notfound": "We could not find that order. Please check your confirmation link.",
      "thanks.notfound2": "We could not find that order. If you just checked out, wait a moment and refresh.",
      "thanks.confirmed": "Order confirmed", "thanks.h1": "Thank you.",
      "thanks.preorder": "This is a preorder. Expected to ship: {date}.",
      "thanks.q": "Questions about your order? Email",

      "lamp.kicker": "Custom", "lamp.h1": "Design your memorial lamp",
      "lamp.lede": "Pick one of the four sides below, then choose a saint illustration or upload your own photo for each side. Every lamp is designed and hand crafted in Montreal from plant-based materials, with a warm flickering glow.",
      "lamp.cancel": "Your checkout was cancelled. Your design is still below.",
      "lamp.s1": "Step 1: choose your four sides",
      "lamp.progress": "{n} of 4 sides chosen.",
      "lamp.notchosen": "Not chosen yet",
      "lamp.nothing": "Nothing chosen yet",
      "lamp.change": "Change side {n}", "lamp.choose": "Choose side {n}",
      "lamp.side": "Side {n}", "lamp.picker_t": "Choose side {n}",
      "lamp.picker_p": "Tap an illustration, or upload your own photo for this side.",
      "lamp.upload_l": "Or upload your own photo",
      "lamp.upload_p": "Your photo is kept only to make your lamp.",
      "lamp.back": "Back to my sides",
      "lamp.uploading": "Uploading your photo...",
      "lamp.upload_err": "Sorry, that photo could not be uploaded. Please try a different image.",
      "lamp.s2": "Step 2: choose your pack",
      "lamp.single": "Single $39.99", "lamp.pack4": "4-pack $99.99",
      "lamp.pack_note": "The 4-pack means 4 lamps of the same design.",
      "lamp.extra_note": "Additional copies of the same design are $24.99 each.",
      "lamp.s3": "Step 3: checkout",
      "lamp.checkout": "Continue to checkout",
      "lamp.secure": "Secure checkout with Stripe. Shipping: $5 Canada, $10 US, $15 worldwide. Delivery: 1-2 weeks. Shipping address collected at checkout.",
      "lamp.ship_country": "Shipping country",
      "lamp.ship_ca": "Canada — $5",
      "lamp.ship_us": "United States — $10",
      "lamp.ship_intl": "International — $15",
      "lamp.gallery_err": "Sorry, the illustration gallery could not be loaded. Please refresh the page.",
      "lamp.need_sides": "Please choose an illustration or photo for side {list} before checking out.",
      "lamp.preparing": "Preparing your checkout...",
      "lamp.start_err": "Sorry, checkout could not start. Please try again.",
      "lamp.yourphoto": "Your photo",

      "priv.kicker": "Privacy", "priv.h1": "Privacy",
      "priv.p1": "ADN Creations collects only what is needed to run the store: your order details, shipping address, and anything you send through the request forms. Payment information is processed securely by Stripe and never touches our servers.",
      "priv.p2": "We count page visits anonymously, by day and page only. No accounts, no tracking cookies, no advertising profiles.",
      "priv.p3": "Your information is never sold or shared with third parties except as required to fulfill your order, such as giving a shipping carrier your address.",
      "priv.p4": "Questions about your data:",

      "terms.kicker": "Terms", "terms.h1": "Terms of sale",
      "terms.p1": "All products are designed and hand crafted by ADN Creations in Montreal, Quebec. Prices are in Canadian dollars.",
      "terms.p2": "Each piece is made to order or finished by hand, so small variations are part of the work. If your order arrives damaged or incorrect, contact us within 14 days and we will make it right.",
      "terms.p3": "Preorders are charged at checkout. The expected ship date shown on the product page is our best estimate; we will email you if it changes.",
      "terms.p4": "Custom engraved items are final sale unless they arrive damaged or do not match the approved text.",
      "terms.p7": "Returns: if a standard piece isn't right for you, contact us within 14 days of delivery for a return or exchange. The item must be unused and in its original packaging; return shipping is at your cost unless the mistake is ours.",
      "terms.p5": "Shipping is flat-rate: $5 in Canada, $10 in the United States, $15 worldwide. Delivery takes 1-2 weeks.",
      "terms.p6": "Contact:",

      "sg.kicker": "Your ideas", "sg.h1": "Suggest a project.",
      "sg.lede": "Have a product idea, a custom project, or a collaboration in mind? Tell us. We read every suggestion.",
      "sg.form_h": "Pitch your idea",
      "sg.name": "Name", "sg.email": "Email",
      "sg.title_l": "Idea title", "sg.title_ph": "e.g. a night-light lamp for babies...",
      "sg.desc_l": "Description", "sg.desc_ph": "Describe your idea in a few sentences.",
      "sg.cat_l": "Category",
      "sg.cat_product": "Product idea", "sg.cat_custom": "Custom work",
      "sg.cat_collab": "Collaboration", "sg.cat_other": "Other",
      "sg.send": "Send my suggestion",
      "sg.ok": "Suggestion received. Thank you, we will reply if your idea is picked up.",
      "sg.err2": "Something went wrong. Please try again.",
      "sg.err3": "Could not send your suggestion. Please try again.",

      "login.title": "Seller login | ADN Creations",
      "login.h": "Seller login",
      "login.user": "Username", "login.pass": "Password",
      "login.submit": "Log in", "login.back": "Back to the site",
      "login.bad": "Wrong username or password.",
      "login.disabled": "Password login is not configured yet. Use your admin link."
    }
  };

  function getLang() {
    try {
      var l = localStorage.getItem("adn_lang");
      if (l === "fr" || l === "en") return l;
    } catch (e) { /* ignore */ }
    var m = document.cookie.match(/(?:^|;\s*)adn_lang=(fr|en)/);
    return m ? m[1] : "fr";
  }

  function setLang(lang) {
    if (lang !== "fr" && lang !== "en") lang = "fr";
    try { localStorage.setItem("adn_lang", lang); } catch (e) { /* ignore */ }
    document.cookie = "adn_lang=" + lang + ";path=/;max-age=31536000;SameSite=Lax";
    applyLang(lang);
  }

  function T(key) {
    var lang = getLang();
    var d = I18N[lang] || I18N.fr;
    return d[key] != null ? d[key] : (I18N.en[key] != null ? I18N.en[key] : key);
  }

  function fmt(s, vars) {
    return String(s).replace(/\{(\w+)\}/g, function (m, k) {
      return vars && vars[k] != null ? vars[k] : m;
    });
  }

  function applyLang(lang) {
    var d = I18N[lang] || I18N.fr;
    document.documentElement.setAttribute("lang", lang);
    var els = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < els.length; i++) {
      var k = els[i].getAttribute("data-i18n");
      if (d[k] != null) els[i].textContent = d[k];
    }
    var htmlEls = document.querySelectorAll("[data-i18n-html]");
    for (var j = 0; j < htmlEls.length; j++) {
      var kh = htmlEls[j].getAttribute("data-i18n-html");
      if (d[kh] != null) htmlEls[j].innerHTML = d[kh];
    }
    var attrEls = document.querySelectorAll("[data-i18n-attr]");
    for (var a = 0; a < attrEls.length; a++) {
      var spec = attrEls[a].getAttribute("data-i18n-attr").split(";");
      for (var b = 0; b < spec.length; b++) {
        var parts = spec[b].split(":");
        if (parts.length === 2 && d[parts[1]] != null) {
          attrEls[a].setAttribute(parts[0], d[parts[1]]);
        }
      }
    }
    var toggles = document.querySelectorAll(".lang-toggle [data-lang]");
    for (var c = 0; c < toggles.length; c++) {
      toggles[c].classList.toggle("on", toggles[c].getAttribute("data-lang") === lang);
    }
    if (typeof window.adnLangChanged === "function") {
      try { window.adnLangChanged(lang); } catch (e) { /* ignore */ }
    }
  }

  function initToggle() {
    var toggles = document.querySelectorAll(".lang-toggle [data-lang]");
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].addEventListener("click", function () {
        setLang(this.getAttribute("data-lang"));
      });
    }
  }

  window.adnGetLang = getLang;
  window.adnSetLang = setLang;
  window.adnApplyLang = applyLang;
  window.adnT = T;
  window.adnFmt = fmt;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initToggle();
      applyLang(getLang());
    });
  } else {
    initToggle();
    applyLang(getLang());
  }
})();
