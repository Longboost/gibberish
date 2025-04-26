from dataclasses import dataclass
from gibberishModules.words import *
from gibberishModules.strings import *

@dataclass
class importDefinition:
    name: str
    identifier: int
    timesUsed: int
    fileID: int
    dataTypeString: str
    unknown0: int
    foundIn: str = None

importDefinitionDict = dict()

dataTypes = {
    0x02: "int",
    0x04: "function",
    0x05: "thread",
    0x07: "function"
}

dataTypesReverse = {value: key for key, value in dataTypes.items()}

def readImportDefinitionsFromKsm(wordsEnumerated: enumerate[int], currentWord: rawWord) -> importDefinition:
    # padding
    getNextWord(wordsEnumerated, currentWord)
    assert currentWord.value == 0xffffffff, hex(currentWord.value)
    
    getNextWord(wordsEnumerated, currentWord)
    if versionRaw < 0x00010302:
        # these are both shorts
        # a counter of how many times this import is used in the file. Purpose not clear
        timesUsed = currentWord.value & 0xffff
        # an id that somehow indicates what file this is imported from. Consistent between different files, but not sure how it is determined
        fileID = currentWord.value >> 16
    else:
        # a counter of how many times this import is used in the file. Purpose not clear
        timesUsed = currentWord.value
        # obsolete
        fileID = None
    
    # dataType
    getNextWord(wordsEnumerated, currentWord)
    dataTypeString = dataTypes[currentWord.value]
    
    # unused?
    if versionRaw < 0x00010302:
        getNextWord(wordsEnumerated, currentWord)
        unknown0 = currentWord.value
    else:
        unknown0 = None
    
    # importID
    getNextWord(wordsEnumerated, currentWord)
    importID = currentWord.value
    
    # unused?
    getNextWord(wordsEnumerated, currentWord)
    assert currentWord.value == 0x00000000, hex(currentWord.value)
    if versionRaw < 0x00010302:
        getNextWord(wordsEnumerated, currentWord)
        assert currentWord.value == 0x00000000, hex(currentWord.value)
    
    # name
    name = readStringFromKsm(wordsEnumerated, currentWord)
        
    return importDefinition(name, importID, timesUsed, fileID, dataTypeString, unknown0), importID

def parseImportDefinitions(section: object, versionRawInput: int):
    global versionRaw
    versionRaw = versionRawInput
    currentWord = rawWord(0, 0)
    wordsEnumerated = enumerate(section.words)
    global importDefinitionDict
    importDefinitionDict = dict()
    for index in range(section.itemCount):
        newDefinition, importID = readImportDefinitionsFromKsm(wordsEnumerated, currentWord)
        importDefinitionDict[importID] = newDefinition

def importDefinitionDictGet(key: int) -> importDefinition | None:
    return importDefinitionDict.get(key, None)

def importDefinitionDictGetAllValues() -> list[importDefinition]:
    return importDefinitionDict.values()

def importDataTypesStringToInt(key: str) -> int | None:
    return dataTypesReverse.get(key, None)