from enum import Enum, IntEnum
from struct import unpack
from dataclasses import dataclass
from gibberishModules.words import *
from gibberishModules.strings import *

versionRaw = None

class variableScope(Enum):
    tempVar = 1
    localVar = 2
    static = 3
    const = 4
    Global = 5
    tempStaticVar = 6

@dataclass
class variable:
    name: str | None
    identifier: int
    alias: str
    value: int | float | str | bool | None
    scope: IntEnum
    dataTypeString: str
    
    def __copy__(self):
        return variable(self.name, self.identifier, self.alias, self.value, self.scope, self.dataTypeString)

variableDict = dict()

dataTypes = {
    0x00: 'float',
    0x01: 'int',
    0x02: 'hex',
    0x03: 'string',
    0x04: 'alloc',
    0x05: 'ref',
    0x06: 'ptr',
    0x07: 'bool',
    0x08: 'func',
    #0x09: 'func',
    0x0a: 'antistring',
    0x0b: 'me',
    0x0c: 'table',
    0x0d: 'none',
    0x0e: 'noinit',
    
    0x14: 'user'
}

dataTypesReverse = {value: key for key, value in dataTypes.items()}

def readVariableFromKsm(wordsEnumerated: enumerate[int], currentWord: rawWord, scope: IntEnum) -> (variable, int):
    # name presence flag
    getNextWord(wordsEnumerated, currentWord)
    hasName = (currentWord.value == 0xffffffff)
    assert (hasName or currentWord.value == 0x00000000), hex(currentWord.value)
    
    # identifier
    getNextWord(wordsEnumerated, currentWord)
    identifier = currentWord.value
    
    # flags
    getNextWord(wordsEnumerated, currentWord)
    flags = currentWord.value
    
    dataTypeString = dataTypes[flags & 0xff]
    
    # value
    getNextWord(wordsEnumerated, currentWord)
    rawValue = currentWord.value
    hasString = False
    match dataTypeString:
        case "float":
            value = unpack('<f', rawValue.to_bytes(4, byteorder='little'))[0]
            value = float('%.6g' % value) # rounding to 6 s.f. unfortunately cannot be made less confusing
        case "int":
            if rawValue >= 0x80000000:
                value = rawValue - 0x100000000
            else:
                value = rawValue    
        case "hex":
            value = rawValue
        case "string":
            assert rawValue == 0, hex(rawValue)
            hasString = True
        case "bool":
            assert rawValue in (0, 1)
            value = bool(rawValue)
        case "object":
            assert rawValue == 0
            value = rawValue
        case _:
            value = rawValue
    
    if hasName:
        name = readStringFromKsm(wordsEnumerated, currentWord)
    else:
        name = None
    
    # string value
    if hasString:
        value = readStringFromKsm(wordsEnumerated, currentWord)
    
    # generated alias
    alias = f"var_{hex(identifier)}"
    return variable(name, identifier, alias, value, scope, dataTypeString), identifier
    
def parseVariables(section: object, scope: IntEnum, versionRawInput: int | None = None):
    if not versionRawInput is None:
        global versionRaw
        versionRaw = versionRawInput
    currentWord = rawWord(0, 0)
    wordsEnumerated = enumerate(section.words)
    global variableDict
    if scope == variableScope.Global:
        assert section.itemCount == 0
    for index in range(section.itemCount):
        newDefinition, variableID = readVariableFromKsm(wordsEnumerated, currentWord, scope)
        variableDict[variableID] = newDefinition

def variableDictGet(key: int, function: object = None) -> variable | None:
    variableMatch = variableDict.get(key, None)
    
    if variableMatch is not None:
        if versionRaw < 0x00010302:
            assert not (bool((key & 0xf0000000) == 0x30000000) ^ (variableMatch.scope == variableScope.static)), hex(key)
            assert not (bool((key & 0xf0000000) == 0x40000000) ^ (variableMatch.scope == variableScope.const)), hex(key)
        return variableMatch
    
    # tempVar
    if (key & 0xffffff00) == 0x10000100:
        tempIdentifier = key & 0xff
        alias = f"tempVar{tempIdentifier}"
        return variable(None, key, alias, 0, variableScope.tempVar, None)    
    # tempStaticVar
    if (key & 0xffffff00) == 0x10000200:
        tempIdentifier = key & 0xff
        alias = f"tStaticVar{tempIdentifier}"
        return variable(None, key, alias, 0, variableScope.tempStaticVar, None)
    # tempVar (as ref)
    if (key & 0xffffff00) == 0x10000400:
        tempIdentifier = key & 0xff
        alias = f"ref tempVar{tempIdentifier}"
        return variable(None, key, alias, 0, variableScope.tempVar, None)
    # localVar
    if (key & 0xffff00ff) == 0x20000000:
        localIdentifier = (key >> 8) & 0xff
        alias = f"localVar{localIdentifier}"
        return variable(None, key, alias, 0, variableScope.localVar, None)
    
    if not versionRaw is None and versionRaw >= 0x00010302:
        variableMatch = function.definedLocals.get(key, None) if function is not None else None
        if variableMatch is not None:
            return variableMatch
        
        if (key & 0xffffff00) == 0x40000100:
            tempIdentifier = key & 0xff
            alias = f"tempVar{tempIdentifier}"
            return variable(None, key, alias, 0, variableScope.tempVar, None)    
    
    return None

def variableDictGetAllValues() -> list[variable]:
    return variableDict.values()

def variableDictGetAllKeys() -> list[int]:
    return variableDict.keys()

def writeVariableValue(value: int | float | str | bool | None, dataTypeString: str) -> str | None:
    match dataTypeString:
        case "string":
            return f'"{value}"'
        case "bool":
            return ("true" if value else "false")
        case "me":
            return "self"
        case "int" | "float":
            return repr(value)
        case "hex":
            return hex(value)
        case _:
            return hex(value)

def isVariableDatatype(key: str) -> bool:
    return key in dataTypes.values()

def variableDataTypesStringToInt(key: str) -> int | None:
    return dataTypesReverse.get(key, None)

def variableDataTypesIntToString(key: int) -> str | None:
    return dataTypes.get(key, None)

def isVariableScope(key: str) -> bool:
    return key in variableScopeEnumIntToStringDict.values()

variableScopeEnumIntToStringDict = {
    variableScope.tempVar: "temp",
    variableScope.localVar: "local",
    variableScope.static: "static",
    variableScope.const: "const",
    variableScope.tempStaticVar: "tstatic"
}

variableScopeStringToEnumIntDict = {value: key for key, value in variableScopeEnumIntToStringDict.items()}

def variableScopeEnumIntToStringDictGet(key: IntEnum) -> str | None:
    return variableScopeEnumIntToStringDict.get(key, None)

def variableScopeStringToEnumIntDictGet(key: str) -> IntEnum | None:
    return variableScopeStringToEnumIntDict.get(key, None)

def getMinimumAndMaxmimumVariableIdentifiers() -> (int, int):
    identifierList = [identifier & 0x0fffffff for identifier in variableDict.keys()]
    if not identifierList:
        return 0xffffffff, 0x00000000
    return min(identifierList), max(identifierList)

def resetVariableDict():
    global variableDict
    variableDict = dict()