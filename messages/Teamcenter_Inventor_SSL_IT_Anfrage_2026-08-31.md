# Teamcenter–Inventor SSL-Problem – IT-Anfrage

**Datum:** 31.08.2026  
**Betreff:** SSL-Zertifikatsproblem beim Öffnen eines BG aus Active Workspace in Inventor

## Nachricht an Teamcenter IT

Guten Tag,

ich kann mich im Active Workspace im Browser mit meinem Account problemlos anmelden.

Beim Öffnen eines BG aus Active Workspace in Inventor erscheint nach der Anmeldung jedoch folgende Meldung:

> Teamcenter server is disconnected.  
> Failed to encrypt/decrypt the service request.  
> SSL certificate problem: self-signed certificate in certificate chain

Bosch VPN ist verbunden. Ich habe den Test zusätzlich mit gestopptem RB Local Proxy sowie nach vollständigem Neustart von Inventor durchgeführt – derselbe Fehler bleibt bestehen.

Können Sie bitte die Teamcenter-Integration in Inventor bzw. deren Server-/SOA-URL und Zertifikatskette prüfen?

Vielen Dank und viele Grüße  
[Name]

## Einordnung

- Active Workspace im Browser funktioniert mit demselben Account.
- Der Fehler tritt vor bzw. unabhängig von einer erfolgreichen Anmeldung in Inventor auf.
- Daher handelt es sich sehr wahrscheinlich nicht um ein Passwort- oder Berechtigungsproblem, sondern um die Zertifikats-/Client-Konfiguration der Teamcenter-Integration in Inventor.
