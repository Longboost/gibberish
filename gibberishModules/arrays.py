from enum import Enum, IntEnum
from dataclasses import dataclass
from gibberishModules.words import *
from gibberishModules.strings import *

class arrayDataType(Enum):
    Variable = 0
    Int = 1
    Float = 2
    Bool = 3

@dataclass
class arrayDefinition:
    name: str
    length: int
    identifier: int
    address: int
    values: list
    dataType: IntEnum

arrayDefinitionDictByAddress = dict()
arrayDefinitionDictByID = dict()
arrayDefinitionDictByName = dict()

def readArrayDefinitionFromKsm(wordsEnumerated: enumerate[int], currentWord: rawWord) -> (arrayDefinition, int, int):
    # padding
    getNextWord(wordsEnumerated, currentWord)
    assert currentWord.value == 0xffffffff, hex(currentWord.value)
    
    # array id
    getNextWord(wordsEnumerated, currentWord)
    identifier = currentWord.value
    
    # datatype - discard
    getNextWord(wordsEnumerated, currentWord)
    
    # length
    getNextWord(wordsEnumerated, currentWord)
    length = currentWord.value
    
    # address
    getNextWord(wordsEnumerated, currentWord)
    address = currentWord.value
    
    # name
    name = readStringFromKsm(wordsEnumerated, currentWord)
    return arrayDefinition(name, length, identifier, address, None, None), address, identifier

def parseArrayDefinitions(section: object):
    currentWord = rawWord(0, 0)
    wordsEnumerated = enumerate(section.words)
    global arrayDefinitionDictByAddress, arrayDefinitionDictByID
    arrayDefinitionDictByAddress = dict()
    arrayDefinitionDictByID = dict()
    for index in range(section.itemCount):
        newDefinition, address, identifier = readArrayDefinitionFromKsm(wordsEnumerated, currentWord)
        arrayDefinitionDictByAddress[address] = newDefinition
        arrayDefinitionDictByID[identifier] = newDefinition
        arrayDefinitionDictByName[newDefinition.name] = newDefinition

def arrayDefinitionDictByAddressGet(key: int, currentFunctionTree: list[object] = []) -> arrayDefinition | None:
    if currentFunctionTree:
        potentialMatch = currentFunctionTree[-1].localArraysByAddress.get(key, None)
        if not potentialMatch is None:
            return potentialMatch
    return arrayDefinitionDictByAddress.get(key, None)

def arrayDefinitionDictByIDGet(key: int, currentFunctionTree: list[object] = []) -> arrayDefinition | None:
    if currentFunctionTree:
        potentialMatch = currentFunctionTree[-1].localArraysByID.get(key, None)
        if not potentialMatch is None:
            return potentialMatch
    return arrayDefinitionDictByID.get(key, None)

def arrayDefinitionDictByNameGet(key: int, currentFunctionTree: list[object] | object = []) -> arrayDefinition | None:
    if currentFunctionTree:
        if isinstance(currentFunctionTree, list):
            potentialMatch = currentFunctionTree[-1].localArraysByName.get(key, None)
        else:
            potentialMatch = currentFunctionTree.localArraysByName.get(key, None)
        if potentialMatch is not None:
            return potentialMatch
    return arrayDefinitionDictByName.get(key, None)

def arrayDefinitionDictByIDGetAllKeys() -> list[int]:
    return arrayDefinitionDictByID.keys()

def getMinimumAndMaxmimumArrayIdentifiers() -> (int, int):
    identifierList = [identifier & 0x0fffffff for identifier in arrayDefinitionDictByID.keys()]
    if not identifierList:
        return 0xffffffff, 0x00000000
    return min(identifierList), max(identifierList)