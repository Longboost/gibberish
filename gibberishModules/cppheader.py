from gibberishModules.imports import importDefinition, importDefinitionDictGetAllValues
from gibberishModules.instructions import importedInstruction, variableInstruction
from gibberishModules.variables import variable, variableDictGetAllValues, variableScope, writeVariableValue, isVariableScope
from gibberishModules.terms import iterableFile

def writeCppHeaderFile(versionRaw: int, minID: int) -> str:
    outstr = ""
    indentLevel = 0
    definedGameFlags = set()
    imports = list(importDefinitionDictGetAllValues())[::-1]
    if minID == -1:
        minID = 0x00100000
    outstr += f"#offset {hex(minID)};\n"
    if versionRaw < 0x00010302:
        for thisImport in imports:
            thisInstruction = importedInstruction(thisImport.identifier, False)
            #outstr += f"#import {thisImport.dataTypeString} {thisImport.name} from {hex(thisImport.fileID)} {{{hex(thisImport.unknown0)} vs {hex(thisImport.identifier)}}};\n"
            outstr += f"#import {thisImport.dataTypeString} {thisImport.name} from {hex(thisImport.fileID)} {{{hex(thisImport.unknown0)}}};\n"
    else:
        for thisImport in imports:
            thisInstruction = importedInstruction(thisImport.identifier, False)
            outstr += f"#import {thisImport.dataTypeString} {thisImport.name};\n"
    
    variables = list(variableDictGetAllValues())[::-1]
    for thisVariable in variables:
        
        if thisVariable.scope != variableScope.static:
            continue
        
        thisInstruction = variableInstruction(thisVariable.identifier, False)
        if thisVariable.dataTypeString == "user":
            if thisVariable.name in definedGameFlags:
                continue
            definedGameFlags.add(thisVariable.name)
            outstr += f"{thisInstruction.writeToCpp(indentLevel)[0]};\n"
            continue
        if thisVariable.dataTypeString in ("float", "int", "string", "bool"):
            outstr += f"{thisInstruction.writeToCpp(indentLevel)[0]} = {writeVariableValue(thisVariable.value, thisVariable.dataTypeString)};\n"
            continue
        
        if thisVariable.dataTypeString == "func":
            #outstr += f"{thisInstruction.writeToCpp(indentLevel)[0]} = {writeVariableValue(thisVariable.value, thisVariable.dataTypeString)};\n"
            continue
        
        assert False, f"Unhandled data type: {thisVariable.dataTypeString}"
    
    return outstr

def parseCppHeaderFile(fileLines: list[str]) -> (dict[importDefinition], dict[variable], int):
    definedImports = dict()
    definedVariables = dict()
    identifierSlotOffset = 0x00100000
    file = iterableFile(fileLines)
    while True:
        file.allowGetNextLine(True, False)
        if file.line is None: break
        
        file.formatCurrentLine()
        
        while file.line == '' or file.line[0] == ';':
            file.allowGetNextLine(True, True)
            if file.line is None: break
            file.formatCurrentLine()
        
        if file.line is None: break
        file.getNextTerm()
        
        
        if file.term == '#':
            outcome = file.readFileParameter()
            if isinstance(outcome, importDefinition):
                newImport = outcome
                definedImports[newImport.name] = newImport
                continue
            identifierSlotOffset = outcome
            continue
        
        if isVariableScope(file.term):
            newVariable = file.readVariable()
            if newVariable.name in definedVariables:
                existingVariable = definedVariables[newVariable.name]
                assert newVariable.scope is None or newVariable.scope == existingVariable.scope, f"Scope specified for \"{newVariable.name}\" on line {self.index+1} conflicts earlier declaration!"
                assert newVariable.dataTypeString is None or newVariable.dataTypeString == existingVariable.dataTypeString, f"Data type specified for \"{newVariable.name}\" on line {self.index+1} conflicts earlier declaration!"
                newVariable = existingVariable
            else:
                definedVariables[newVariable.name] = newVariable
            
            try:
                if file.allowGetNextLine(True, False):
                    continue
            except StopIteration:
                break
            
            file.getNextTerm()
            assert file.term == "=", f"Expected \"=\" but instead got \"{file.term}\" on line {file.index+1}"
            file.getNextTerm()
            newVariable.value, _ = file.readConstValue()
            
    return definedImports, definedVariables, identifierSlotOffset