from gibberishModules.words import *

def readStringFromKsm(wordsEnumerated: enumerate[int], currentWord: rawWord) -> str:
    getNextWord(wordsEnumerated, currentWord)
    stringWordLength = currentWord.value
    byteText = bytes()
    for _ in range(stringWordLength):
        getNextWord(wordsEnumerated, currentWord)
        byteText += currentWord.value.to_bytes(4, byteorder='little')
    if b'\x00' in byteText:
        byteText = byteText[:byteText.index(b'\x00')]
    text = byteText.decode('utf-8')
    return text

def writeStringToKsm(section: object, string: str):
    string = string.encode('utf-8')
    string += b"\x00" * (4 - (len(string) % 4))
    stringWordLength = len(string) // 4
    section.words.append(stringWordLength)
    section.words.frombytes(string)