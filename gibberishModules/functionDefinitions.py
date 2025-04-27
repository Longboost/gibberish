from dataclasses import dataclass, field
from gibberishModules.words import *
from gibberishModules.strings import *
from gibberishModules.arrays import arrayDefinition, readArrayDefinitionFromKsm
from gibberishModules.variables import variable, readVariableFromKsm, variableScope, variableDataTypesIntToString

labelAliasSuffixes = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'

@dataclass
class label:
    identifier: int
    address: int
    alias: str

@dataclass
class functionDefinition:
    name: str
    identifier: int
    isPublic: bool
    tempVarFlags: list[bool]
    accumulatorID: int
    accumulator: variable
    labelsByAddress: dict[int, label]
    labelsByID: dict[int, label]
    localArraysByAddress: dict[int, arrayDefinition]
    localArraysByID: dict[int, arrayDefinition]
    definedLocals: dict[int, variable] | None
    declaredLocals: set[int] | list[variable]
    specialLabel: label | None
    codeOffset: int | None
    codeEnd: int | None
    localArraysByName: dict[str, arrayDefinition] = field(default_factory=dict)
    localVariableTypes: list[str] = field(default_factory=list)

functionDefinitionDict = dict()

def readFunctionDefinitionFromKsm(wordsEnumerated: enumerate[int], currentWord: rawWord) -> (functionDefinition, int):
    # padding
    getNextWord(wordsEnumerated, currentWord)
    assert currentWord.value == 0xffffffff, hex(currentWord.value)
    
    # function id
    getNextWord(wordsEnumerated, currentWord)
    functionID = currentWord.value
    
    # whether the function can be called by other scripts
    getNextWord(wordsEnumerated, currentWord)
    isPublic = bool(currentWord.value)
    
    if versionRaw < 0x00010302:
        # which tempVars are present
        getNextWord(wordsEnumerated, currentWord)
        tempVarFlagsRaw = currentWord.value
        tempVarFlags = [bool((tempVarFlagsRaw >> i) & 1) for i in range(32)]
        del tempVarFlagsRaw
    else:
        tempVarFlags = [True] * 32
    
    # code offset - discard
    getNextWord(wordsEnumerated, currentWord)
    # code end - discard
    getNextWord(wordsEnumerated, currentWord)
    
    # the variable that handles storing any values returned by any called instructions run in the function
    # ideally you should avoid accessing this variable directly
    getNextWord(wordsEnumerated, currentWord)
    accumulatorID = currentWord.value
    
    # special label???
    getNextWord(wordsEnumerated, currentWord)
    #assert currentWord.value == 0x00000000
    specialLabelID = currentWord.value
    
    # name
    name = readStringFromKsm(wordsEnumerated, currentWord)
    
    # local variables - discard
    getNextWord(wordsEnumerated, currentWord)
    localVariableCount = currentWord.value
    localVariableTypes = list()
    if versionRaw < 0x00010302:
        definedLocals = None
        for _ in range(localVariableCount):
            getNextWord(wordsEnumerated, currentWord)
            getNextWord(wordsEnumerated, currentWord)
            getNextWord(wordsEnumerated, currentWord)
            localVariableTypes.append(variableDataTypesIntToString(currentWord.value))
            getNextWord(wordsEnumerated, currentWord)
    else:
        definedLocals = dict()
        for _ in range(localVariableCount):
            newLocal, newLocalIdentifier = readVariableFromKsm(wordsEnumerated, currentWord, variableScope.localVar)
            definedLocals[newLocalIdentifier] = newLocal
    
    # local arrays
    getNextWord(wordsEnumerated, currentWord)
    localArrayCount = currentWord.value
    localArraysByAddress = dict()
    localArraysByID = dict()
    localArraysByName = dict()
    for i in range(localArrayCount):
        newDefinition, address, identifier = readArrayDefinitionFromKsm(wordsEnumerated, currentWord)
        localArraysByAddress[address] = newDefinition
        localArraysByID[identifier] = newDefinition
        localArraysByName[newDefinition.name] = newDefinition
    
    # labels
    getNextWord(wordsEnumerated, currentWord)
    labelCount = currentWord.value
    labelsByID = dict()
    labelsByAddress = dict()
    for labelIndex in range(labelCount):
        getNextWord(wordsEnumerated, currentWord)
        assert currentWord.value == 0x00000000, hex(currentWord.value)
        getNextWord(wordsEnumerated, currentWord)
        labelID = currentWord.value
        getNextWord(wordsEnumerated, currentWord)
        labelAddress = currentWord.value
        labelAlias = f"label{labelAliasSuffixes[labelCount - labelIndex - 1]}"
        theLabel = label(labelID, labelAddress, labelAlias)
        labelsByID[labelID] = theLabel
        labelsByAddress[labelAddress] = theLabel
    if labelCount > 0:
        del labelIndex, labelID, labelAddress, labelAlias
    if specialLabelID != 0x00000000:
        specialLabel = labelsByID[specialLabelID]
    else:
        specialLabel = None
    return functionDefinition(name, functionID, isPublic, tempVarFlags, accumulatorID, None, labelsByAddress, labelsByID, localArraysByAddress, localArraysByID, definedLocals, {accumulatorID}, specialLabel, None, None, localArraysByName, localVariableTypes), functionID

def parseFunctionDefinitions(section: object, versionRawInput: int):
    global versionRaw
    versionRaw = versionRawInput
    currentWord = rawWord(0, 0)
    wordsEnumerated = enumerate(section.words)
    global functionDefinitionDict
    functionDefinitionDict = dict()
    for index in range(section.itemCount):
        newDefinition, functionID = readFunctionDefinitionFromKsm(wordsEnumerated, currentWord)
        functionDefinitionDict[functionID] = newDefinition

def functionDefinitionDictGet(key: int) -> functionDefinition | None:
    return functionDefinitionDict.get(key, None)

def functionDefinitionDictGetAllKeys() -> list[int]:
    return functionDefinitionDict.keys()

def getAllLabelAndArrayIDs() -> list[int]:
    identifierList = list()
    for functionDefinition in functionDefinitionDict.values():
        identifierList.extend(functionDefinition.labelsByID)
        identifierList.extend(functionDefinition.localArraysByID)
    return identifierList

def getMinimumAndMaxmimumFunctionIdentifiers() -> (int, int):
    identifierList = [identifier & 0x0fffffff for identifier in functionDefinitionDict.keys()]
    if not identifierList:
        return 0xffffffff, 0x00000000
    for functionDefinition in functionDefinitionDict.values():
        identifierList.extend(labelID & 0x0fffffff for labelID in functionDefinition.labelsByID)
        identifierList.extend(labelID & 0x0fffffff for labelID in functionDefinition.localArraysByID)
    return min(identifierList), max(identifierList)