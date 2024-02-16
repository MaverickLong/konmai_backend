from gpapi.googleplay import GooglePlayAPI

import time
import os
import json
import requests
import sys
import re

# Load templates, configs and emulators
api26Server = GooglePlayAPI("ja_JP", "Asia/Tokyo", "old_rubens")
api31Server = GooglePlayAPI("ja_JP", "Asia/Tokyo", "rubens")

urlList = {"Files": []}

headers = {'Accept': 'application/vnd.github+json',
           'Authorization': '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'}

with open("./config.json", "r", encoding="UTF-8") as text:
    config = json.load(text)
    text.close()

with open("./passwd.json", "r", encoding="UTF-8") as text:
    passwd = json.load(text)
    text.close()

headers = {'Accept': 'application/vnd.github+json',
           'Authorization': passwd['GitHubToken']}

updated = False


def removeAllFiles(delPath):
    delList = os.listdir(delPath)
    for file in delList:
        filePath = os.path.join(delPath, file)
        if os.path.isfile(filePath):
            os.remove(filePath)


def tryFunc(func, default=0):
    try:
        return func()
    except:
        return default


def updateConfig(gameName, locale, subversionInfo):
    with open("./config.json", "r", encoding="UTF-8") as text:
        currentConfig = json.load(text)
        text.close()
    currentConfig["packages"][gameName][locale] = subversionInfo
    dumpedConfig = json.dumps(
        currentConfig, indent=4, separators=(",", ": "), ensure_ascii=False
    )

    with open("./config.json", "w", encoding="UTF-8") as text:
        text.write(dumpedConfig)
        text.close()


def doGithubUpdate(gameName, subversionInfo):
    global updated
    response = requests.get(subversionInfo["url"], headers=headers)
    if response.json()["tag_name"] != subversionInfo["versionString"]:
        print("Update found for " + gameName + " Github, triggering APK download...")
        subversionInfo["versionString"] = response.json()["tag_name"]
        for files in response.json()["assets"]:
            if re.search(subversionInfo["pattern"], files["browser_download_url"]) != None:
                updated = True
                apk = requests.get(files["browser_download_url"], headers=headers)
                tryFunc(lambda: os.mkdir("./temp/" + subversionInfo["packageName"]))
                removeAllFiles("./temp/" + subversionInfo["packageName"] + "/")
                with open(
                    "./temp/"
                    + subversionInfo["packageName"]
                    + "/"
                    + subversionInfo["packageName"]
                    + "_"
                    + subversionInfo["versionString"]
                    + "."
                    + subversionInfo["suffix"],
                    "wb",
                ) as file:
                    file.write(apk.content)
                for serverInfo in config["servers"].items():
                    if (
                        serverInfo[0] in subversionInfo["allocatedServer"]
                        and tryFunc(lambda: serverInfo[1]["push"], "true") == "true"
                    ):
                        os.system(
                            "scp -C -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r -P "
                            + serverInfo[1]["sshPort"]
                            + ' "./temp/'
                            + subversionInfo["packageName"]
                            + '/" '
                            + tryFunc(lambda: serverInfo[1]["userName"], "root")
                            + "@"
                            + serverInfo[1]["domain"]
                            + ":"
                            + serverInfo[1]["webRoot"]
                        )
                return (True, subversionInfo)
    return (False, subversionInfo)


def doArcaeaUpdate(subversionInfo):
    global updated
    res = requests.get(
        "https://webapi.lowiro.com/webapi/serve/static/bin/arcaea/apk"
    ).json()
    if res["success"]:
        if res["value"]["version"] != subversionInfo["versionString"]:
            subversionInfo["versionString"] = res["value"]["version"]
            print("Update found for Arcaea C, triggering APK download...")
            updated = True
            apkName = "moe.low.arc_" + res["value"]["version"] + ".apk"
            with open(apkName, "wb") as apk:
                dlApk = requests.get(url=res["value"]["url"], stream=True)
                for chunk in dlApk.iter_content(chunk_size=5242880):
                    if chunk:
                        apk.write(chunk)
                apk.close()
            for serverInfo in config["servers"].items():
                if (
                    serverInfo[0] in subversionInfo["allocatedServer"]
                    and tryFunc(lambda: serverInfo[1]["push"], "true") == "true"
                ):
                    os.system(
                        "scp -C -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r -P "
                        + serverInfo[1]["sshPort"]
                        + " "
                        + apkName
                        + " "
                        + tryFunc(lambda: serverInfo[1]["userName"], "root")
                        + "@"
                        + serverInfo[1]["domain"]
                        + ":"
                        + serverInfo[1]["webRoot"]
                        + "/moe.low.arc/"
                    )
            if os.path.isfile(apkName):
                os.remove(apkName)
            return (True, subversionInfo)
    else:
        print("Get Arcaea C update failed")

    return (False, subversionInfo)


def doGooglePlayUpgrade(subversionInfo):
    packageName = subversionInfo["packageName"]
    versionString = subversionInfo["versionString"]
    allocatedServer = subversionInfo["allocatedServer"]

    # Create Folder
    tryFunc(lambda: os.mkdir("./temp/" + packageName))

    # Download game files
    try:
        download = api26Server.download(packageName, expansion_files=True)
    except:
        if debug:
            print(
                "download via old api failed for "
                + packageName
                + ", switching to new api"
            )
        download = api31Server.download(packageName, expansion_files=True)

    # Write base APK file
    apkPath = packageName + "/" + packageName + "_" + versionString + ".apk"
    with open("./temp/" + apkPath, "wb") as first:
        for chunk in download.get("file").get("data"):
            first.write(chunk)

    splitAPK = False

    for splits in download["splits"]:
        splitAPK = True
        splitPath = packageName + "/" + splits["name"] + ".apk"
        with open("./temp/" + splitPath, "wb") as third:
            for chunk in splits.get("file").get("data"):
                third.write(chunk)

    if splitAPK:
        # print("Generating APKS File")
        os.system("mv ./temp/" + apkPath + " ./temp/" + packageName + "/base.apk")
        apkPath = apkPath + "s"
        os.system("zip -j -r ./temp/" + apkPath + " ./temp/" + packageName + "/*.apk")
        os.system("rm ./temp/" + packageName + "/*.apk")
        subversionInfo["suffix"] = "apks"
    else:
        subversionInfo["suffix"] = "apk"

    # print("Extracting datapacks...")

    obbDict = {}
    obbList = []

    # Write OBB file
    for obb in download["additionalData"]:
        obbPath = (
            packageName
            + "/"
            + obb["type"]
            + "."
            + str(obb["versionCode"])
            + "."
            + download["docId"]
            + ".obb"
        )
        obbDict[obb["type"]] = obbPath

        obbList.append((obb["type"], obbPath))

        with open("./temp/" + obbPath, "wb") as second:
            for chunk in obb.get("file").get("data"):
                second.write(chunk)

    for serverInfo in config["servers"].items():
        if (
            serverInfo[0] in allocatedServer
            and tryFunc(lambda: serverInfo[1]["push"], "true") == "true"
        ):
            os.system(
                "scp -C -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r -P "
                + serverInfo[1]["sshPort"]
                + " ./temp/"
                + packageName
                + "/ "
                + tryFunc(lambda: serverInfo[1]["userName"], "root")
                + "@"
                + serverInfo[1]["domain"]
                + ":"
                + serverInfo[1]["webRoot"]
            )

    subversionInfo["obb"] = obbDict

    removeAllFiles("./temp/" + packageName + "/")

    return subversionInfo


def fetchInfo(packageName, server):
    details = server.details(packageName)
    # try:
    newVersion = details["details"]["appDetails"]["versionCode"]
    # except Exception:
    #    print("fetch info failed for game " + packageName)
    versionString = details["details"]["appDetails"]["versionString"]
    return (newVersion, versionString)


def checkUpdate(subversion, gameName):
    global updated

    locale, subversionInfo = subversion

    packageName = subversionInfo["packageName"]

    manualMode = tryFunc(lambda: subversionInfo["manualMode"], False)

    source = tryFunc(lambda: subversionInfo["source"], "GP")

    server = api26Server

    versionString = subversionInfo["versionString"]

    if source == "GitHub":
        (updatedGame, subversionInfo) = doGithubUpdate(gameName, subversionInfo)
        if updatedGame:
            updateConfig(gameName, locale, subversionInfo)
        return

    if source == "arc":
        (updatedGame, subversionInfo) = doArcaeaUpdate(subversionInfo)
        if updatedGame:
            updateConfig(gameName, locale, subversionInfo)
        return

    if not manualMode:
        try:
            version = subversionInfo["version"]
        except:
            print("fetch version failed for" + packageName)
            return
        # Fetch game version
        forceHighApi = tryFunc(lambda: subversionInfo["forceHighApi"], "false")
        if forceHighApi == "true":
            server = api31Server
        try:
            newVersion, versionString = fetchInfo(packageName, server)
        except:
            try:
                if debug:
                    print(
                        "fetch new version via old api failed for game "
                        + packageName
                        + ", using new api..."
                    )
                server = api31Server
                newVersion, versionString = fetchInfo(packageName, server)
            except:
                if debug:
                    print("fetch new version failed for game " + packageName)
                newVersion = -1

    if not manualMode and version < int(newVersion):
        subversionInfo["version"] = newVersion
        subversionInfo["versionString"] = versionString
        print(
            "Update found for "
            + gameName
            + " "
            + locale
            + " "
            + str(newVersion)
            + ", triggering APK download..."
        )
        subversionInfo = doGooglePlayUpgrade(subversionInfo)
        updateConfig(gameName, locale, subversionInfo)
        updated = True


try:
    api26Server.login(gsfId=passwd["gsfId26"], authSubToken=passwd["authSubToken26"])
except Exception as gsfException:
    #print("Login via gsfId failed for API 26, backporting to password login.")
    #print(time.asctime(time.localtime(time.time())))
    try:
        passwd["gsfId26"], passwd["authSubToken26"] = api26Server.login(
            passwd["email"], passwd["password"], returnParams=True
        )
    except Exception as passwdException:
        print("Login failed. Something has gone wrong:\n" + str(passwdException))
        exit(-1)
    #print("Password Login Success, new details has been stored.")

try:
    api31Server.login(gsfId=passwd["gsfId31"], authSubToken=passwd["authSubToken31"])
except Exception as gsfException:
    #print("Login via gsfId failed for API 31, backporting to password login.")
    #print(time.asctime(time.localtime(time.time())))
    try:
        passwd["gsfId31"], passwd["authSubToken31"] = api31Server.login(
            passwd["email"], passwd["password"], returnParams=True
        )
    except Exception as passwdException:
        print("Login failed. Something has gone wrong:\n" + str(passwdException))
        exit(-1)
    #print("Password Login Success, new details has been stored.")

with open("passwd.json", "w", encoding="UTF-8") as text:
    passwdList = json.dumps(
        passwd, indent=4, separators=(",", ": "), ensure_ascii=False
    )
    text.write(passwdList)
    text.close()

debug = len(sys.argv) > 1 and sys.argv[1] == "debug"

for game in config["packages"].items():
    # Load game details from config
    gameName = game[0]
    gameSubversions = game[1]

    # Skipping april fools "game" items.
    if "configs" in gameSubversions:
        if "aprilFools" in gameSubversions["configs"]:
            continue

    for subversion in gameSubversions.items():
        checkUpdate(subversion, gameName)

if updated:
    print("Finally, pushing index markdown to frontend")
    os.system("nohup bash up.sh")
else:
    pass

with open("/data/api/urls.json", "w", encoding="UTF-8") as text:
    dumpedUrlList = json.dumps(
        urlList, indent=4, separators=(",", ": "), ensure_ascii=False
    )
    text.write(dumpedUrlList)
    text.close()