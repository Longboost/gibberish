from dataclasses import dataclass
import array
import sys
import os
from struct import pack
from importlib import reload
from gibberishModules.instructions import *
from gibberishModules.words import *
from gibberishModules.functionDefinitions import *
from gibberishModules.imports import *
from gibberishModules.arrays import *
from gibberishModules.variables import *
from gibberishModules.cppheader import writeCppHeaderFile, parseCppHeaderFile
from gibberishModules.cppbody import parseCppBodyFile
from gibberishModules.strings import writeStringToKsm

@dataclass
class fileSection:
    itemCount: int
    words: array.array[int]
    
def readHeader(fileWords: array.array[int]) -> list[array.array[int]]:
    assert fileWords[0] == 0x524d534b, fileWords[0]
    global versionRaw, versionText
    versionRaw = fileWords[1]
    setInstructionsVersionRaw(versionRaw)
    assert versionRaw in (0x00010300, 0x00010302), fileWords[1]
    majorVersion = (versionRaw >> 16) & 0xffff
    minorVersion = (versionRaw >> 8) & 0xff
    patchVersion = versionRaw & 0xff
    versionText = f"{majorVersion}.{minorVersion}.{patchVersion}"
    headerWords = fileWords[2:11]
    headerWords[-1] = len(fileWords)
    sections = [fileSection(fileWords[startAddress], fileWords[startAddress + 1:endAddress]) for startAddress, endAddress in zip(headerWords[:-1], headerWords[1:])]
    return sections

def parseSummary(section: fileSection) -> str | None:
    if versionRaw <= 0x00010300:
        return None
    assert section.itemCount == 0xffffffff, hex(section.itemCount)
    currentWord = rawWord(0, 0)
    wordsEnumerated = enumerate(section.words)
    #TODO: figure out, discard for now
    getNextWord(wordsEnumerated, currentWord)
    #filename
    fileName = readStringFromKsm(wordsEnumerated, currentWord)
    return fileName

def parseInstructions(section: fileSection) -> str:
    currentWord = rawWord(0, 0)
    wordsEnumerated = enumerate(section.words)
    outstr = ""
    indentLevel = 0
    
    while currentWord.index < section.itemCount - 1:
        getNextWord(wordsEnumerated, currentWord)
        
        if (currentWord.value & 0xffff0000) or (currentWord.value & 0xff > 0xa0):
            instructionID = currentWord.value
            disableExpression = False
            
            thisInstruction = variableInstruction(instructionID, disableExpression)
        else:
            instructionID = currentWord.value & 0xff
            disableExpression = bool(currentWord.value & 0x0100)
            
            thisInstruction = matchInstruction(instructionID, False)(instructionID, disableExpression)
        
        if isinstance(thisInstruction, endFileInstruction):
            assert currentWord.index == section.itemCount - 1, hex(currentWord.index * 4)
            break
        
        thisInstruction.readFromKsm(wordsEnumerated, currentWord)
        cppText, indentLevel, indentOffsetNextLine = thisInstruction.writeToCpp(indentLevel)
        if cppText.endswith('\n'):
            cppText = '\t' * indentLevel + cppText[:-1].replace('\n', f"\n{'\t' * indentLevel}") + "\n"
        outstr += cppText
        
        indentLevel += indentOffsetNextLine
        indentOffsetNextLine = 0
    return outstr    

def getMinimumAndMaximumIdentifiers() -> (int, int):
    variableMin, variableMax = getMinimumAndMaxmimumVariableIdentifiers()
    functionMin, functionMax = getMinimumAndMaxmimumFunctionIdentifiers()
    arrayMin, arrayMax = getMinimumAndMaxmimumArrayIdentifiers()
    finalMin = min(variableMin, functionMin, arrayMin)
    finalMax = max(variableMax, functionMax, arrayMax)
    
    #ensure no variable overlap
    identifierList = list()
    identifierList.extend(variableDictGetAllKeys())
    identifierList.extend(functionDefinitionDictGetAllKeys())
    identifierList.extend(arrayDefinitionDictByIDGetAllKeys())
    identifierList.extend(getAllLabelAndArrayIDs())
    identifierList = [identifier & 0x00ffffff for identifier in identifierList]
    identifierSet = set(identifierList)
    assert len(identifierList) == len(identifierSet)
    
    if finalMin == 0xffffffff:
        return -1, -1
    return finalMin, finalMax
    
def parseIDTest2():
    path = sys.argv[1]
    importList = list()
    for root, dirNames, fileNames in os.walk(path):
        for fileName in fileNames:
            resetVariableDict()
            fullFileName = f"{root}\\{fileName}"
            rawFile = open(fullFileName, "rb").read()
            fileWords = array.array("L", rawFile)
            try:
                sections = readHeader(fileWords)
                parseFunctionDefinitions(sections[1], versionRaw)
                parseVariables(sections[2], variableScope.static, versionRaw)
                parseArrayDefinitions(sections[3])
                parseVariables(sections[4], variableScope.const)
                parseImportDefinitions(sections[5], versionRaw)
                parseVariables(sections[6], variableScope.Global)
            except:
                fullFileName = fullFileName.removeprefix(path)
            else:
                fullFileName = fullFileName.removeprefix(path)
                extList = list(importDefinitionDictGetAllValues())
                for thisImport in extList:
                    thisImport.foundIn = fullFileName
                importList.extend(extList)
    outFileA = ""
    outFileB = ""
    outFileC = ""
    importNameSet = set()
    for thisImport in importList:
        if thisImport.name in importNameSet:
            continue
        importNameSet.add(thisImport.name)
        fileIDtext = hex(thisImport.fileID)
        fileIDtext = "0x" + ("0" * (6 - len(fileIDtext))) + fileIDtext[2:] + "\n"
        outFileA += fileIDtext
        outFileB += thisImport.name + "\n"
        outFileC += thisImport.foundIn + "\n"
    filename = "listA.txt"
    open(filename, "w", encoding='utf-8').write(outFileA)
    filename = "listB.txt"
    open(filename, "w", encoding='utf-8').write(outFileB)
    filename = "listC.txt"
    open(filename, "w", encoding='utf-8').write(outFileC)
    
def parseIDTest():
    path = sys.argv[1]
    idRangeList = list()
    for root, dirNames, fileNames in os.walk(path):
        for fileName in fileNames:
            resetVariableDict()
            fullFileName = f"{root}\\{fileName}"
            rawFile = open(fullFileName, "rb").read()
            fileWords = array.array("L", rawFile)
            try:
                sections = readHeader(fileWords)
                parseFunctionDefinitions(sections[1], versionRaw)
                parseVariables(sections[2], variableScope.static, versionRaw)
                parseArrayDefinitions(sections[3])
                parseVariables(sections[4], variableScope.const)
                parseImportDefinitions(sections[5], versionRaw)
                parseVariables(sections[6], variableScope.Global)
            except:
                fullFileName = fullFileName.removeprefix(path)
                idRangeList.append((-2, -2, fullFileName))
            else:
                fullFileName = fullFileName.removeprefix(path)
                minID, maxID = getMinimumAndMaximumIdentifiers()
                idRangeList.append((minID, maxID, fullFileName))
    idRangeList.sort(key=lambda x: x[0])
    lastMaxID = None
    outFile = ""
    for minID, maxID, fullFileName in idRangeList:
        if minID == -1:
            outFile += f"NONE - {fullFileName}\n"
        elif minID == -2:
            outFile += f"ERR - {fullFileName}\n"
        else:
            outFile += f"{hex(minID // 8)} - {fullFileName}\n"
            lastMaxID = maxID
    filename = "list.txt"
    open(filename, "w", encoding='utf-8').write(outFile)

def parseFindInstruction(path: str, targetInstructionID: int):
    setTargetInstructionID(targetInstructionID)
    outFile = ""
    for root, dirNames, fileNames in os.walk(path):
        for fileName in fileNames:
            resetVariableDict()
            setTargetInstructionFound(False)
            fullFileName = f"{root}\\{fileName}"
            rawFile = open(fullFileName, "rb").read()
            fileWords = array.array("L", rawFile)
            try:
                sections = readHeader(fileWords)
                parseFunctionDefinitions(sections[1], versionRaw)
                parseVariables(sections[2], variableScope.static, versionRaw)
                parseArrayDefinitions(sections[3])
                parseVariables(sections[4], variableScope.const)
                parseImportDefinitions(sections[5], versionRaw)
                parseVariables(sections[6], variableScope.Global)
                writeCppHeaderFile(versionRaw)
                parseInstructions(sections[7])
            except:
                fullFileName = fullFileName.removeprefix(path)
                outFile += f"ERROR - {fullFileName}\n"
            else:
                fullFileName = fullFileName.removeprefix(path)
                if getTargetInstructionFound():
                    outFile += f"FOUND - {fullFileName}\n"
            print(f"{fullFileName} processed.")
    filename = "list.txt"
    open(filename, "w", encoding='utf-8').write(outFile)

def parseFindAllInstructions(path: str):
    setTargetInstructionID("all")
    outFile = "ERROR:\n"
    fileNameSetList = [list() for count in range(0xa1)]
    for root, dirNames, fileNames in os.walk(path):
        for fileName in fileNames:
            resetVariableDict()
            resetFoundInstructionsSet()
            fullFileName = f"{root}\\{fileName}"
            rawFile = open(fullFileName, "rb").read()
            fileWords = array.array("L", rawFile)
            try:
                sections = readHeader(fileWords)
                parseFunctionDefinitions(sections[1], versionRaw)
                parseVariables(sections[2], variableScope.static, versionRaw)
                parseArrayDefinitions(sections[3])
                parseVariables(sections[4], variableScope.const)
                parseImportDefinitions(sections[5], versionRaw)
                parseVariables(sections[6], variableScope.Global)
                writeCppHeaderFile(versionRaw)
                parseInstructions(sections[7])
            except:
                fullFileName = fullFileName.removeprefix(path)
                outFile += f"  - {fullFileName}\n"
            else:
                fullFileName = fullFileName.removeprefix(path)
                for instructionID in getTargetInstructionFound():
                    assert instructionID >= 0x00 and instructionID <= 0xa0
                    fileNameSetList[instructionID].append(fullFileName)
            print(f"{fullFileName} processed.")
    for instructionID, fileNameList in enumerate(fileNameSetList):
        outFile += f"INSTRUCTION_{hex(instructionID)}:\n"
        for fileName in fileNameList:
            outFile += f"  - {fileName}\n"
    filename = "list.yaml"
    open(filename, "w", encoding='utf-8').write(outFile)

def buildSummarySection(section: fileSection, importCount: int, allowDisableExpression: bool):
    section.words.append(0x00000000)
    infoWord = min(importCount, 0xff) | (allowDisableExpression << 16)
    section.words.append(infoWord)

def buildVariableDefinition(section: fileSection, thisVariable: variable):
    buildWithName = (thisVariable.dataTypeString in ("func", "user"))
    section.words.append(0xffffffff if buildWithName else 0x00000000)
    section.words.append(thisVariable.identifier)
    flags = variableDataTypesStringToInt(thisVariable.dataTypeString)
    match thisVariable.scope:
        case variableScope.localVar:
            pass
        case variableScope.static:
            if thisVariable.dataTypeString == "user":
                flags |= 0x08000000
            else:
                flags |= 0x02000000
        case variableScope.const:
            flags |= 0x04000000
    section.words.append(flags)
    match thisVariable.dataTypeString:
        case "float":
            section.words.frombytes(pack("f", thisVariable.value))
        case "int":
            if thisVariable.value < 0:
                thisVariable.value += 0x100000000
            section.words.append(thisVariable.value)
        case "hex":
            section.words.append(thisVariable.value)
        case "string" | "me" | "user" | "func" | "ref":
            section.words.append(0x00000000)
        case "bool":
            section.words.append(1 if thisVariable.value else 0)
        case _:
            raise Exception(f"Unhandled data type: {thisVariable.dataTypeString}")
    if buildWithName:
        writeStringToKsm(section, thisVariable.name)
    if thisVariable.dataTypeString == "string":
        writeStringToKsm(section, thisVariable.value)

def buildFunctionDefinitionsSection(section: fileSection, definedFunctions: dict):
    dataTypeBack = {
        arrayDataType.Variable: 0,
        arrayDataType.Int: 1,
        arrayDataType.Float: 2,
        arrayDataType.Bool: 3
    }
    
    section.itemCount = len(definedFunctions)
    for function in list(definedFunctions.values())[::-1]:
        section.words.append(0xffffffff)
        section.words.append(function.identifier)
        section.words.append(int(function.isPublic))
        tempVarFlagsRaw = sum(bit << index for index, bit in enumerate(function.tempVarFlags))
        section.words.append(tempVarFlagsRaw)
        del tempVarFlagsRaw
        section.words.append(function.codeOffset)
        section.words.append(function.codeEnd)
        section.words.append(function.accumulatorID)
        if not function.specialLabel is None:
            section.words.append(function.specialLabel.identifier)
        else:
            section.words.append(0x00000000)
        writeStringToKsm(section, function.name)
        section.words.append(len(function.declaredLocals))
        for localVariable in function.declaredLocals:
            buildVariableDefinition(section, localVariable)
        
        section.words.append(len(function.localArraysByID))
        for thisArray in function.localArraysByID.values():
            section.words.append(0xffffffff)
            section.words.append(thisArray.identifier)
            section.words.append(dataTypeBack[thisArray.dataType])
            section.words.append(thisArray.length)
            section.words.append(thisArray.address)
            writeStringToKsm(section, thisArray.name)
        
        section.words.append(len(function.labelsByID))
        for thisLabel in list(function.labelsByID.values())[::-1]:
            section.words.append(0)
            section.words.append(thisLabel.identifier)
            section.words.append(thisLabel.address)

def buildVariableDefinitionSection(section: fileSection, usedIdentifierSlots: list, scope: int):
    for thisVariable in usedIdentifierSlots[::-1]:
        if isinstance(thisVariable, variable) and thisVariable.scope == scope:
            section.itemCount += 1
            buildVariableDefinition(section, thisVariable)

def buildArrayDefinitionSection(section: fileSection, usedIdentifierSlots: list):
    dataTypeBack = {
        arrayDataType.Variable: 0,
        arrayDataType.Int: 1,
        arrayDataType.Float: 2,
        arrayDataType.Bool: 3
    }
    
    for thisArray in usedIdentifierSlots[::-1]:
        if isinstance(thisArray, arrayDefinition):
            section.itemCount += 1
            section.words.append(0xffffffff)
            section.words.append(thisArray.identifier)
            section.words.append(dataTypeBack[thisArray.dataType])
            section.words.append(thisArray.length)
            section.words.append(thisArray.address)
            writeStringToKsm(section, thisArray.name)

def buildImportDefinitionSection(section: fileSection, usedImportSlots: list):
    section.itemCount = len(usedImportSlots)
    for thisImport in usedImportSlots[::-1]:
        section.words.append(0xffffffff)
        combinedParameter = (thisImport.timesUsed | (thisImport.fileID << 16))
        section.words.append(combinedParameter)
        del combinedParameter
        section.words.append(importDataTypesStringToInt(thisImport.dataTypeString))
        section.words.append(thisImport.unknown0)
        section.words.append(thisImport.identifier)
        section.words.append(0x00000000)
        section.words.append(0x00000000)
        writeStringToKsm(section, thisImport.name)

def buildInstructionSection(section: fileSection, instructionList: list):
    for thisInstruction in instructionList:
        #print(type(thisInstruction))
        thisInstruction.writeToKsm(section)
    for thisInstruction in instructionList:
        thisInstruction.writeToKsmAfter(section)
    section.itemCount = len(section.words)

def buildHeaderSection(section: fileSection, sections: list[fileSection]):
    section.words.append(0x524d534b)
    section.words.append(0x00010300)
    offset = 0x0b
    for thisSection in sections:
        section.words.append(offset)
        offset += len(thisSection.words) + 1
    section.words.append(0x00000000)

def main():
    def helperText():
        print("""Usage:
    python main.py <file>.bin       - parses a KSM *.bin file and outputs it to *.cksm and *.hksm
    python main.py <file>.cksm      - parses a *.cksm file (and respective *.hksm file) and builds into KSM *.bin""")
    
    if len(sys.argv) == 3 and sys.argv[2] == "-idtest":
        parseIDTest()
        return
    if len(sys.argv) == 3 and sys.argv[2] == "-idtest2":
        parseIDTest2()
        return
    if len(sys.argv) == 4 and sys.argv[2] == "-findinstruction":
        if sys.argv[3].lower() == "all":
            parseFindAllInstructions(sys.argv[1])
        else:
            parseFindInstruction(sys.argv[1], int(sys.argv[3], 0))
        return
    if len(sys.argv) != 2:
        helperText()
        return
    if sys.argv[1].endswith(".bin"):
        rawFile = open(sys.argv[1], "rb").read()
        fileWords = array.array("L", rawFile)
        sections = readHeader(fileWords)
        filename = parseSummary(sections[0])
        parseFunctionDefinitions(sections[1], versionRaw)
        parseVariables(sections[2], variableScope.static, versionRaw)
        parseArrayDefinitions(sections[3])
        parseVariables(sections[4], variableScope.const)
        parseImportDefinitions(sections[5], versionRaw)
        parseVariables(sections[6], variableScope.Global)
        outHeaderFile = writeCppHeaderFile(versionRaw)
        outFile = parseInstructions(sections[7])
        
        if filename is None:
            filename = f"{sys.argv[1].removesuffix(".bin")}.cksm"
        open(filename, "w", encoding='utf-8').write(outFile)

        filename = f"{filename.removesuffix(".cksm")}.hksm"
        open(filename, "w", encoding='utf-8').write(outHeaderFile)
        return
    if sys.argv[1].endswith(".cksm"):
        fileName = sys.argv[1]
        headerFileName = f"{fileName.removesuffix(".cksm")}.hksm"
        
        fileText = open(headerFileName, "r", encoding = "utf-8").readlines()
        definedImports, definedVariables, identifierSlotOffset = parseCppHeaderFile(fileText)
        
        fileText = open(fileName, "r", encoding = "utf-8").readlines()
        instructionList, definedFunctions, usedIdentifierSlots, usedImportSlots, importCount, allowDisableExpression = parseCppBodyFile(fileText, definedImports, definedVariables, identifierSlotOffset)
        
        #print(definedImports.keys())
        #print("\n".join(f"{value}" for value in definedVariables.values()))
        #print([f.name for f in definedFunctions.values()])
        #print([f.isPublic for f in definedFunctions.values()])
        sections = [fileSection(0, array.array("L")) for sectionCount in range(9)]
        buildInstructionSection(sections[7], instructionList)
        buildSummarySection(sections[0], importCount, allowDisableExpression)
        buildFunctionDefinitionsSection(sections[1], definedFunctions)
        buildVariableDefinitionSection(sections[2], usedIdentifierSlots, variableScope.static)
        buildArrayDefinitionSection(sections[3], usedIdentifierSlots)
        buildVariableDefinitionSection(sections[4], usedIdentifierSlots, variableScope.const)
        buildImportDefinitionSection(sections[5], usedImportSlots)
        buildVariableDefinitionSection(sections[6], usedIdentifierSlots, variableScope.Global)
        buildHeaderSection(sections[-1], sections[:-1])
        outFile = bytearray()
        outFile += sections[-1].words.tobytes()
        for section in sections[:-1]:
            section.words.insert(0, section.itemCount)
            outFile += section.words.tobytes()
        filename = f"{sys.argv[1].removesuffix(".cksm")}.re.bin"
        open(filename, "wb").write(outFile)
        return
    
    helperText()
    return

if __name__ == "__main__": main()